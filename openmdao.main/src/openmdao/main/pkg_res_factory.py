
import logging
import copy
import os.path

# these fail to find pkg_resources when run from pylint
# pylint: disable-msg=F0401
import pkg_resources
from pkg_resources import get_entry_map, get_distribution, working_set
from pkg_resources import Environment, WorkingSet, Requirement, DistributionNotFound
    
from openmdao.main.factory import Factory
from openmdao.util.dep import plugin_groups
                
class PkgResourcesFactory(Factory):
    """A Factory that loads plugins using the pkg_resources API, which means
    it searches through egg info of distributions in order to find any entry
    point groups corresponding to openmdao plugin types, e.g.,
    openmdao.component, openmdao.variable, etc.
    """
    
    def __init__(self, groups=plugin_groups.keys(), search_path=None):
        super(PkgResourcesFactory, self).__init__()
        self._have_new_types = True
        self._groups = copy.copy(groups)
        self._search_path = search_path
        self.env = Environment(search_path)
            
    def create(self, typ, version=None, server=None, 
               res_desc=None, **ctor_args):
        """Create and return an object of the given type, with
        optional name, version, server id, and resource description.
        """
        if server is not None or res_desc is not None:
            return None

        classes = self._get_type_dict()
            
        try:
            lst = classes[typ]
            dist = lst[0]
            groups = lst[1]
            klass = dist.load_entry_point(groups[0], typ)
            
            if version is not None and dist.version != version:
                return None
            
            return klass(**ctor_args)
        except KeyError:
            if self._search_path is None:
                return None
            # try to look in the whole environment
            for group in self._groups:
                for proj in self.env:
                    for dist in self.env[proj]:
                        if version is not None and version != dist.version:
                            continue
                        ep = dist.get_entry_info(group, typ)
                        if ep is not None:
                            dist.activate()
                            klass = ep.load(require=True, env=self.env)
                            self._have_new_types = True
                            return klass(**ctor_args)
                        if version is None:
                            # newest version didn't have entry point, so skip to next project
                            break
        return None
            
    def _entry_map_info(self, distiter):
        dct = {}
        for group in plugin_groups.keys():
            for dist in distiter:
                d = dist.get_entry_map(group)
                for name in d:
                    lst = dct.setdefault(name, [dist, []])
                    lst[1].append(group)
        return dct
        
    def _get_type_dict(self):
        if self._have_new_types:
            self._entry_pt_classes = self._entry_map_info(working_set)
        return self._entry_pt_classes
            
    def _get_meta_info(self, typ_list, groups, typ_dict):
        distset = set()
        for name, lst in typ_dict.items():
            dist = lst[0]
            distset.add(dist.project_name)
            ifaces = set()
            for g in lst[1]:
                ifaces.update(plugin_groups[g])
            meta = {
                'version': dist.version,
                'ifaces': list(ifaces),
            }
            if groups.intersection(lst[1]):
                typ_list.append((name, meta))
        return distset
        
    def get_available_types(self, groups=None):
        """Return a set of tuples of the form (typename, dist_version), one
        for each available plugin type in the given entry point groups.
        If groups is None, return the set for all openmdao entry point groups.
        """
        ret = []
        
        if groups is None:
            groups = plugin_groups.keys()
        groups = set(groups)
        
        typ_dict = self._get_type_dict()
        distset = self._get_meta_info(ret, groups, typ_dict)
           
        if self._search_path is None: # self.env has same contents as working_set,
                                      # so don't bother looking through it
            return ret

        # now look in the whole Environment
        dists = [] # we want an iterator of newest dist for each project in Environment
        for proj in self.env:
            dist = self.env[proj][0]
            if dist.project_name not in distset:
                dists.append(dist)
        
        typ_dict = self._entry_map_info(dists)
        dset = self._get_meta_info(ret, groups, typ_dict)
        
        return ret

