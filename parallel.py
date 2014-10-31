from argparse import ArgumentParser
from os.path import join, basename, relpath
from csv import writer, DictReader
from StringIO import StringIO
from logging import getLogger
from glob import glob

from boto import connect_s3
from openaddr import paths, jobs

parser = ArgumentParser(description='Run some source files.')
parser.add_argument('-l', '--logfile', help='Optional log file name.')

if __name__ == '__main__':

    args = parser.parse_args()
    jobs.setup_logger(args.logfile)
    
    bucket = connect_s3().get_bucket('openaddresses-cfa')
    
    # Find existing cache information
    state_key = bucket.get_key('state.txt')
    source_extras1 = dict()

    if state_key:
        state_file = StringIO(state_key.get_contents_as_string())
        rows = DictReader(state_file, dialect='excel-tab')
        
        for row in rows:
            key = join(paths.sources, row['source'])
            source_extras1[key] = dict(cache=row['cache'],
                                       version=row['version'],
                                       fingerprint=row['fingerprint'])
    
    getLogger('openaddr').info('Loaded {} sources from state.txt'.format(len(source_extras1)))

    # Cache data, if necessary
    source_files1 = glob(join(paths.sources, '*.json'))
    results1 = jobs.run_all_caches(source_files1, source_extras1, 'openaddresses-cfa')
    
    # Proceed only with sources that have a cache
    source_files2 = [s for s in source_files1 if results1[s].cache]
    source_extras2 = dict([(s, results1[s].todict()) for s in source_files2])
    results2 = jobs.run_all_conforms(source_files2, source_extras2, 'openaddresses-cfa')

    # Gather all results
    state_file = StringIO()
    out = writer(state_file, dialect='excel-tab')
    
    out.writerow(('source', 'cache', 'version', 'fingerprint', 'processed'))
    
    for source in source_files1:
        result1 = results1[source]
        result2 = results2.get(source, dict(processed=None, path=None))
    
        out.writerow((relpath(source, paths.sources), result1.cache,
                      result1.version, result1.fingerprint,
                      result2['processed']))
    
    state_data = state_file.getvalue()
    state_args = dict(policy='public-read', headers={'Content-Type': 'text/plain'})
    bucket.new_key('state.txt').set_contents_from_string(state_data, **state_args)
    
    getLogger('openaddr').info('Wrote {} sources to state.txt'.format(len(source_files1)))