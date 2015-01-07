import re
import datetime

# Maximum number of days Misfit will allow in a date range api request
DAYS_IN_CHUNK = 30

def cc_to_underscore(name):
    """ Convert camelCase name to under_score """
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def cc_to_underscore_keys(dictionary):
    """ Convert dictionary keys from camelCase to under_score """
    return dict((cc_to_underscore(key), val) for key, val in dictionary.items())


def chunkify_dates(start, end, days_in_chunk=DAYS_IN_CHUNK):
    """
    Return a list of tuples that chunks the date range into ranges
    of length days_in_chunk, inclusive of the end date. So the end
    date of one chunk is equal to the start date of the chunk after.
    """
    chunks = []
    s = start
    e = start + datetime.timedelta(days=days_in_chunk)
    while e - datetime.timedelta(days=days_in_chunk) < end:
        e = min(e, end)
        chunks.append((s, e))
        s = e
        e = s + datetime.timedelta(days=days_in_chunk)
    return chunks


def dedupe_by_field(l, field):
    """
    Returns a new list with duplicate objects removed. Objects are equal
    iff the have the same value for 'field'.
    """
    d = dict((getattr(obj, field), obj) for obj in l)
    return list(d.values())
