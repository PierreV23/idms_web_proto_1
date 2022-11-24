import time
from irods.models import Resource, ResourceMeta
from irods.column import Criterion
from . import iqry
from app.irodssessions import irods_manager
from app.constants import *

class Tier:
    """A storage tier, corresponding to an iRODS resource
    """
    def __init__(self, tier, resourcename):
        self.tiernumber = tier
        self.resourcename = resourcename
        self._resourcetags = []
        self._available = True
        self._availabilty_check_time = 0
        self.refresh()

    def refresh(self):
        self._resourcetags = []
        meta = iqry.qresmetadict(self.resourcename)
        for key in meta:
            if key.startswith(ATTR_RESOURCE_PREFIX) and meta[key] == 'true':
                self._resourcetags.append(key)

    def available(self):
        """Check if resource is available and enabled
        Only returns true if 'sys::resource::available' and 'sys::resource::enabled' are present and
        have the value 'true'
        """
        enabled = self._hastags(ATTR_RESOURCE_ENABLED)
        available = self._hastags(ATTR_RESOURCE_AVAILABLE)
        return available and enabled

    def hastags(self, tags):
        """Returns true if tags in <tags> are all present in resourcetags
        """
        if isinstance(tags, str):
            taglist = [tags]
        else:
            taglist = tags
        if self._resourcetags:
            present = True
            for tag in list(taglist):
                if not tag in self._resourcetags:
                    present = False
            return present
        else:
            return False

    def __eq__(self, other):
        return self.resourcename == other.resourcename

    def __repr__(self):
        return 'T{}: {}'.format(self.tiernumber, self.resourcename)

class Tierlist:
    """A list of tier objects for a specified tier_group
    """
    def __init__(self, tier_group):
        self.tiers = []
        with irods_manager.session() as session:
            q = session.query(Resource.name, ResourceMeta).filter(
                Criterion('=', ResourceMeta.name, ATTR_TIERING_GROUP)).filter(
                Criterion('=', ResourceMeta.value, tier_group))
        for row in q:
            self.add(Tier(tier=int(row[ResourceMeta.units]), resourcename=row[Resource.name]))

    def add(self, tier):
        self.tiers.append(tier)

    def get(self, tiernumber):
        """Return a tier from the list  by number
        """
        for tier in self.tiers:
            if tier.tiernumber == tiernumber:
                return tier
        return None

    def byname(self, resourcename):
        for tier in self.tiers:
            if tier.resourcename == resourcename:
                return tier
        return None


    def preferred_list(self, tag=None, notag=[], available_only=False):
        """Returns a list of tiers, ordered by tiernumber

        Args:
            tag: list of tags that should be present to be included
            notag: list of tags that should not be present in order to be included
            available_only: Return only available tiers
        Returns:
            ordered list of tier objects
        """
        if tag:
            stiers = [ t for t in self.tiers if t.hastags(tag) ]
        else:
            stiers = self.tiers
        ctiers = []
        for t in stiers:
            add =True
            for t2 in notag:
                if t.hastags(t2):
                    add = False
            if add:
                ctiers.append(t)
        result = sorted(ctiers, key = lambda x: x.tiernumber)
        if available_only:
            result = [ tier for tier in result if tier.available() ]
        return result

    def tag_present(self, type_query):
        """ Returns true if any of the tiers in the list has all tags in type_query
        """
        tagged_tiers = [ t for t in self.tiers if t.hastags(type_query) ]
        return bool(tagged_tiers)

    def __iter__(self):
        return iter(self.tiers)

class TierState:
    Present = '1'
    Partial = '?'
    Absent = '0'
    Unknown = '.'

class IntTierState:
    T = 'T'
    d = 'd'
    D = 'D'

class iState:
    """Internal state of data in the different tiers
    """
    def __init__(self, tiers, state=None):
        """
        Args:
            state: string representation of data presence per tier, e.g. '110'.
        """
        self._state = {}
        self._tiers = tiers
        for tier in tiers:
            self._state[tier.tiernumber] = set()
        if state:
            for i, s in enumerate(state):
                if s == '1':
                    tier = self._tiers.get(i+1)
                    if tier.hastags(ATTR_RESOURCE_TAR):
                        self.set(tier, IntTierState.T )
                    else:
                        self.set(tier, IntTierState.D)

    def set(self, tier, tierstate):
        self._state[tier.tiernumber].add(tierstate)

    def clear(self, tier, tierstate):
        if tierstate in self._state[tier.tiernumber]:
            self._state[tier.tiernumber].remove(tierstate)
    
    def isset(self, tier, tierstate):
        return tierstate in self._state[tier.tiernumber]

    def ispresent(self, tierstate):
        present = False
        for tier in self._tiers:
            present = present or self.isset(tier, tierstate)
        return present

    def equal_for_tierstate(self, other, tierstate):
        """ Compare states for only a single tierstate (T,t,d)
        """
        equal = True
        for tier in self._tiers:
            equal = equal and (self.isset(tier, tierstate) == other.isset(tier, tierstate))
        return equal

    def tag_present(self, type_query):
        """ Returns true if any of the tiers in the list has all tags in type_query
        """
        for nr in self._state:
            if self._state[nr] and self._tiers.get(nr).hastags(type_query):
                return True
        return False

    def state_repr(self):
        """Return state representation as string.

        Similar to __repr__(), except that for present data there is no 
        separate symbol to distinguish between data in TAR form or data objects
        (i.e. "T" or "D" is always "1", "0" for no data, "?" for partial data)
        """
        tier_symbols = []
        for tier in self._tiers.preferred_list():
            if (self.isset(tier, IntTierState.T) and tier.hastags(ATTR_RESOURCE_TAR)) or \
                self.isset(tier, IntTierState.D):
                tier_symbols.append(TierState.Present)
            elif self.isset(tier, IntTierState.d):
                tier_symbols.append(TierState.Partial)
            else:
                tier_symbols.append(TierState.Absent)
        return ''.join(tier_symbols)

    def __repr__(self):
        result = ''
        sorted_tiers = self._tiers.preferred_list()
        for tier in sorted_tiers:
            if self.isset(tier, IntTierState.D):
                s1 = 'D'
            elif self.isset(tier, IntTierState.d):
                s1 = 'd'
            else:
                s1 = '0'
            if self.isset(tier, IntTierState.T):
                s2 = 'T'
            else:
                s2 = '0'
            result = '{}{}{}{}'.format(result, '-' if result else '', s1, s2)
        return result

    def __eq__(self, other):
        return str(self.__repr__) == str(other.__repr__)
