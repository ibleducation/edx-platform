"""
Monitoring utilities which aren't used by the application by default, but can
be used as needed to troubleshoot problems.
"""

import itertools
import logging
import os
from StringIO import StringIO
from collections import defaultdict

import objgraph
from django.conf import settings

indices = defaultdict(itertools.count)

# The directory in which graph files will be created.
GRAPH_DIRECTORY_PATH = settings.MEMORY_GRAPH_DIRECTORY

# The max number of object types for which to show data on the console
MAX_CONSOLE_ROWS = 20

# The max number of object types for which to generate reference graphs
MAX_GRAPHED_OBJECT_TYPES = 5

# Maximum depth of forward reference graphs
REFS_DEPTH = 3

# Maximum depth of backward reference graphs
BACK_REFS_DEPTH = 8

# Max number of objects per type to use as starting points in the reference graphs
MAX_OBJECTS_PER_TYPE = 5

# Object type names for which graphs should not be generated even if the new
# object count is high.  "set" is ignored by default because many sets are
# created in the course of tracking the number of new objects of each type.
IGNORED_TYPES = ('set',)

log = logging.getLogger(__name__)


def show_memory_leaks(
        label=u'memory_leaks',
        max_console_rows=MAX_CONSOLE_ROWS,
        max_graphed_object_types=MAX_GRAPHED_OBJECT_TYPES,
        refs_depth=REFS_DEPTH,
        back_refs_depth=BACK_REFS_DEPTH,
        max_objects_per_type=MAX_OBJECTS_PER_TYPE,
        ignored_types=IGNORED_TYPES,
        graph_directory_path=GRAPH_DIRECTORY_PATH):
    """
    Call this function to get data about memory leaks; what objects are being
    leaked, where did they come from, and what do they contain?  The leaks
    are measured from the last call to ``objgraph.get_new_ids()`` (which is
    called within this function).  Some data is printed to stdout, and more
    details are available in graphs stored at the paths printed to stdout.
    Subsequent calls with the same label are indicated by an increasing index
    in the filename.

    Args:
        label (unicode): The start of the filename for each graph
        max_console_rows (int): The max number of object types for which to
            show data on the console
        max_graphed_object_types (int): The max number of object types for
            which to generate reference graphs
        refs_depth (int): Maximum depth of forward reference graphs
        back_refs_depth (int): Maximum depth of backward reference graphs
        max_objects_per_type (int): Max number of objects per type to use as
            starting points in the reference graphs
        ignored_types (iterable): Object type names for which graphs should
            not be generated even if the new object count is high.
        graph_directory_path(unicode): The directory in which graph files
            will be created.  It will be created if it doesn't already exist.
    """
    new_objects_output = StringIO()
    new_ids = objgraph.get_new_ids(limit=max_console_rows, file=new_objects_output)
    log.info('\n' + new_objects_output.getvalue())
    index = indices[label].next() + 1
    sorted_by_count = sorted(new_ids.items(), key=lambda entry: len(entry[1]), reverse=True)

    if not os.path.exists(graph_directory_path):
        os.makedirs(graph_directory_path)

    for item in sorted_by_count[:max_graphed_object_types]:
        type_name = item[0]
        object_ids = new_ids[type_name]
        if type_name in ignored_types or not object_ids:
            continue
        objects = objgraph.at_addrs(object_ids)[:max_objects_per_type]
        data = {'dir': graph_directory_path, 'label': label,
                'pid': os.getpid(), 'index': index, 'type_name': type_name}

        path = os.path.join(graph_directory_path, u'{label}_{pid}_{index}_{type_name}_backrefs.dot'.format(**data))
        objgraph.show_backrefs(objects, max_depth=back_refs_depth, filename=path)
        log.info('Generated memory graph at {}'.format(path))

        path = os.path.join(graph_directory_path, u'{label}_{pid}_{index}_{type_name}_refs.dot'.format(**data))
        objgraph.show_refs(objects, max_depth=refs_depth, filename=path)
        log.info('Generated memory graph at {}'.format(path))
