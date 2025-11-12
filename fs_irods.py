#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue May  7 12:14:23 2019

@author: Erwin van Wieringen
"""

import base64
import os
import calendar as cal
import irods.keywords as kw
import math
from irods.column import Criterion
from irods.session import iRODSSession
from irods.models import Collection, CollectionMeta, DataObject
from synchelper import utc2local
from fs_base import *

class irodsFsBuilder:
    def __init__(self):
        self._instance = None
        
    def __call__(self, **kwargs):
        if not self._instance:
            self._instance = fs_irods(**kwargs)
        return self._instance
    
factory.register('irods', irodsFsBuilder())


class file_irods(fsobject_base):
    def __init__(self, fso, path):
        super().__init__(fso, path)
        self.irods_object = fso.irods_session.data_objects.get(path)

    def isdir(self):
        return False

    def checksum(self):
        sha2 = self.irods_object.checksum.split(':')[1]
        return base64.b64decode(sha2).hex()

    def filesize(self):
        return self.irods_object.size

    def create_time(self):
        return self.irods_object.create_time

    def owner_name(self):
        return self.irods_object.owner_name

    def isfile(self):
        return True

    def open(self, mode):
        return self.irods_object.open(mode)

    def set_mtime(self, mtime):
        new_time = utc2local(mtime)
        self.irods_object.manager.modDataObjMeta(
            {"objPath": self.path}, {"dataModify": round(new_time)})

    def utc_mtime(self):
        mtime = cal.timegm(self.irods_object.modify_time.timetuple())
        return math.floor(mtime)

    def local_mtime(self):
        return 0


class folder_irods(fsobject_base):
    def __init__(self, fso, path):
        super().__init__(fso, path)
        self.irods_object = fso.irods_session.collections.get(path)

    def isdir(self):
        return True
    
    def isfile(self):
        return False    

    def removemeta(self, name):
        for m in self.irods_object.metadata.get_all(name):
            self.irods_object.metadata.remove(m)

    def setmeta(self, name, value, units=''):
        self.irods_object.metadata.add(name, value, units)

    def replaceorsetmeta(self, name, value):
        self.removemeta(name)
        self.setmeta(name, value)

    def getmeta(self, name):
        return self.irods_object.metadata.get_one(name).value

    def getorsetmeta(self, name, default):
        if not self.irods_object.metadata.get_all(name):
            self.setmeta(name, default, '')
        return self.getmeta(name)

    #def create_time(self2):
    #    return self.irods_object.create_time

    #def owner_name(self2):
    #    return self.irods_object.owner_name


class fs_irods(fs_base):
    def __init__(self, resource='', session=None):
        super().__init__(supportsopen=True)

        self.irods_session = session
        self.resource = resource

    def cleanup(self):
        self.irods_session.cleanup()

    def ls(self, path):
        result = []
        coll = self.irods_session.collections.get(path)
        for subcoll in coll.subcollections:
            result.append(folder_irods(self, subcoll.path))
        for entry in coll.data_objects:
            result.append(self.getfile(entry.path))
        return result
    
    def lsdirnames(self, path):
        if path[-1] == '/':
            path = path[:-1]
        coll = self.irods_session.collections.get(path)
        result = [ subcoll.name for subcoll in coll.subcollections]
        return result

    def lsfilenames(self, path):
        if path[-1] == '/':
            path = path[:-1]        
        coll = self.irods_session.collections.get(path)
        result = [ data_object.name for data_object in coll.data_objects]
        return result

    def lsdirs(self, path):
        print("lsdirs not implemented")
        exit(2)

    def deletefile(self, path):
        if self.fileexists(path):
            file = self.irods_session.data_objects.unlink(path)

    def fileexists(self, path):
        base, file = self._pathsplit(path)
        query = self.irods_session.query(
            Collection.name, DataObject.name).filter(
                Criterion('=', Collection.name, base)).filter(
                    Criterion('=', DataObject.name, file))
        return bool(list(query.get_results()))

    def findfolder(self, name, meta=[]):
        result = []
        query = self.irods_session.query(Collection.name).filter(
                        Criterion('like', Collection.name, '%/' + name))
        for m in meta:
            query = query.filter(
                Criterion('=', CollectionMeta.name, m['field'])).filter(
                    Criterion(m['op'], CollectionMeta.value, m['value']))
        for coll in query.get_results():
            result.append(folder_irods(self, coll[Collection.name]))
        return result

    def folderexists(self, path):
        query = self.irods_session.query(Collection).filter(
            Criterion('=', Collection.name, path))
        return bool(list(query.get_results()))

    def _getfile(self, path):
        return file_irods(self, path)

    def getfolder(self, path):
        return folder_irods(self, path)

    def mkdir(self, path):
        self.irods_session.collections.create(path)
        return folder_irods(self, path)

    def rmdir(self, path, recurse=False, force=False):
        if self.folderexists(path):
            self.irods_session.collections.remove(path, recurse=recurse, force=force)

    def open(self, path, mode):
        options = {kw.FORCE_FLAG_KW: ''}
        obj = self.irods_session.data_objects.create(path, **options,
                                                     resource=self.resource)
        return obj.open(mode[:1])

    def verify(self, checksums, path, exclude=[]):
        print('Verifying checksums')
        for a in checksums:
            if a in exclude:
                continue
            fullpath = path + '/' + a
            if not self.fileexists(fullpath):
                print('Cannot find %s' % fullpath)
                return False
            if checksums[a] != self.getfile(fullpath).checksum():
                print('Checksum error for %s' % fullpath)
                return False
        return True
