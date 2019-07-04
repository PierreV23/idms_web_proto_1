"""
Created on Mon May  6 14:28:12 2019
@author: Erwin van Wieringen
Purpose: abstract filesystem base class
"""

from abc import ABC, abstractmethod
import hashlib

BUF_SIZE = 1024 * 1024

class fsfactory():
    def __init__(self):
        self._fscreators = {}
        
    def register(self, name, creator):
        self._fscreators[name] = creator
        
    def getfs(self, name, **params):
        creator = self._fscreators.get(name)
        if not creator:
            raise ValueError(name)
        return creator(**params)
    
    def listfs(self):
        for i in self._fscreators:
            print(i)

        
factory = fsfactory()
    

class fsobject_base(ABC):
    def __init__(self, fso, path):
        self.fso = fso
        self.path = path
        self._sha256 = ""

    @abstractmethod
    def isdir(self):
        pass

    @abstractmethod
    def isfile(self):
        pass

    def _checksum(self):
        sha256 = hashlib.sha256()
        with fopen(self, 'rb') as f:
            while True:
                data = f.read(BUF_SIZE)
                if not data:
                    break
                sha256.update(data)
        return sha256.hexdigest()

    def checksum(self):
        if self._sha256 == "":
            if self.path in self.fso.checksums:
                self._sha256 = self.fso.checksums[self.path]
            else:
                self._sha256 = self._checksum()
        return self._sha256

    def compareto(self, other):
        if self.filesize() == other.filesize():
            if self.utc_mtime() == other.utc_mtime():
                if self.checksum() == other.checksum():
                    return True
        return False

    def copyto(self, fp):
        source = self.open('rb')
        while True:
            copy_buffer = source.read(BUF_SIZE)
            if not copy_buffer:
                break
            fp.write(copy_buffer)

    def open(self, mode):
        print("fsobject_base.open")
        raise('fs_base.open not implemented')
        exit(2)

    def shortname(self):
        return self.path.split('/')[-1]


class fopen():
    def __init__(self, ff, mode):
        self.objf = ff
        self.mode = mode

    def __enter__(self):
        self.fp = self.objf.open(self.mode)
        return self.fp

    def __exit__(self, type, value, traceback):
        self.fp.close()


class fs_base(ABC):
    @abstractmethod
    def __init__(self, supportsopen=False):
        self.supportsopen = supportsopen
        self.checksums = {}
        self.files = {}

    def add_checksum_file(self, checksums, base):
        for a in checksums:
            print(base + '/' + a)
            print(checksums[a])
            self.checksums[base + '/' + a] = checksums[a]

    @abstractmethod
    def ls(self, path):
        pass

    def lsdirs(self, path):
        result = [ a for a in self.ls(path) if a.isdir() ]
        print('lsdirs %s' % path)
        return result

    def _pathsplit(self, path):
        spath = path.split('/')
        base = '/' + '/'.join(spath[1:-1])
        return base, spath[-1]

    @abstractmethod
    def fileexists(self, path):
        pass

    @abstractmethod
    def folderexists(self, path):
        pass

    @abstractmethod
    def _getfile(self, path):
        return fsobject_base(self, path)

    def getfile(self, path):
        if path not in self.files:
            self.files[path] = self._getfile(path)
        return self.files[path]

    @abstractmethod
    def mkdir(self, path):
        pass

    def read_checksum_file(self, path):
        result = {}
        csFile = self.getfile(path)
        with csFile.open('r') as fh:
            for x in fh:
                hashvalue, filename = x.split('  ')
                result[filename.rstrip()] = hashvalue
        return result

    def syncfolderto(self, sourcepath, destfs, destpath):
        print("sync_folder %s to %s" % (sourcepath, destpath))

        copyCounter = 0

        if not destfs.folderexists(destpath):
            destfs.mkdir(destpath)

        for entry in self.ls(sourcepath):
            destfile = destpath + '/' + entry.shortname()
            if entry.isdir():
                if not entry.shortname() in ['.', '..']:
                    self.syncfolderto(entry.path, destfs, destfile)
            else:
                bcopy = False
                if not destfs.fileexists(destfile):
                    print('Destination not found')
                    bcopy = True
                elif not entry.compareto(destfs.getfile(destfile)):
                    print('Comparison failed')
                    bcopy = True
                if bcopy:
                    print('-> Copy %s to %s' % (entry.path, destfile))
                    copyCounter += 1
                    if destfs.supportsopen:
                        with destfs.open(destfile, "wb") as fp_dest:
                            entry.copyto(fp_dest)
                    elif self.supportsopen():
                        with entry.open("rb") as fp_source:
                            destfs.copyfrom(fp_source, destfile)
                    else:
                        print('Error: cannot copy %s to %s' % (entry.shortname(), destfile))
                        exit(2)

                    destfs.getfile(destfile).set_mtime(entry.utc_mtime())

        return copyCounter
