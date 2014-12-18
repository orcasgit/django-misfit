import re
import datetime

def cc_to_underscore(name):
    """ Convert camelCase name to under_score """
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def cc_to_underscore_keys(dictionary):
    """ Convert dictionary keys from camelCase to under_score """
    return dict((cc_to_underscore(key), val) for key, val in dictionary.items())


def chunkify_dates(start, end, days_in_chunk):
    """
    Return a list of tuples that chunks the date range into ranges
    of length days_in_chunk.
    """
    chunks = []
    s = start
    e = start + datetime.timedelta(days=days_in_chunk)
    while e - datetime.timedelta(days=30) < end:
        e = min(e, end)
        chunks.append((s, e))
        s = e + datetime.timedelta(days=1)
        e = s + datetime.timedelta(days=days_in_chunk)
    return chunks
