#!/usr/bin/python
# -*- coding: utf-8 -*-

from dateutil.parser import parse
import os

import pytplot

from .download_files_utilities import *
from .orbit_time import orbit_time
from .maven_kp_to_tplot import maven_kp_to_tplot

def maven_filenames(filenames=None,
                    instruments=None,
                    level='l2',
                    insitu=True,
                    iuvs=False,
                    start_date='2014-01-01',
                    end_date='2020-01-01',
                    update_prefs=False,
                    only_update_prefs=False,
                    local_dir=None):
    """
    This function identifies which MAVEN data to download.
    """

    # Check for orbit num rather than time string
    if isinstance(start_date, int) and isinstance(end_date, int):
        start_date, end_date = orbit_time(start_date, end_date)
        start_date = parse(start_date)
        end_date = parse(end_date)
        start_date = start_date.replace(hour=0, minute=0, second=0)
        end_date = end_date.replace(day=end_date.day+1, hour=0, minute=0, second=0)
        start_date = start_date.strftime('%Y-%m-%d')
        end_date = end_date.strftime('%Y-%m-%d')
        
    if update_prefs or only_update_prefs:
        set_new_data_root_dir()
        if only_update_prefs:
            return
    
    public = get_access()
    if not public:
        get_uname_and_password()

    if filenames is None:
        if insitu and iuvs:
            print("Can't request both INSITU and IUVS in one query.")
            return
        if not insitu and not iuvs:
            print("If not specifying filename(s) to download, Must specify either insitu=True or iuvs=True.")
            return
        
    if instruments is None:
        instruments = ['kp']
        if insitu:
            level = 'insitu'
        if iuvs:
            level = 'iuvs'

    # Set data download location
    if local_dir is None:
        mvn_root_data_dir = get_root_data_dir()
    else:
        mvn_root_data_dir = local_dir

    # Keep track of files to download
    maven_files = {}
    for instrument in instruments:
        # Build the query to the website
        query_args = []
        query_args.append("instrument=" + instrument)
        query_args.append("level=" + level)
        if filenames is not None:
            query_args.append("file=" + filenames)
        query_args.append("start_date=" + start_date)
        query_args.append("end_date=" + end_date)
        if level == 'iuvs':
            query_args.append("file_extension=tab")

        data_dir = os.path.join(mvn_root_data_dir, 'maven', 'data', 'sci', instrument, level)
        
        query = '&'.join(query_args)
        
        s = get_filenames(query, public)

        if not s:
            print("No files found for {}.".format(instrument))
            maven_files[instrument] = []
            continue

        s = s.split(',')

        maven_files[instrument] = [s, data_dir, public]

    # Grab KP data too, there is a lot of good ancillary info in here
    if instruments != 'kp':
        instrument='kp'
        # Build the query to the website
        query_args = []
        query_args.append("instrument=kp")
        query_args.append("level=insitu")
        query_args.append("start_date=" + start_date)
        query_args.append("end_date=" + end_date)
        data_dir = os.path.join(mvn_root_data_dir, 'maven', 'data', 'sci', 'kp', 'insitu')
        query = '&'.join(query_args)
        s = get_filenames(query, public)
        if not s:
            print("No files found for {}.".format(instrument))
            maven_files[instrument] = []
        else:
            s = s.split(',')
            maven_files[instrument] = [s, data_dir, public]

    return maven_files


def load_data(filenames=None,
              instruments=None,
              level='l2',
              type=None,
              insitu=True,
              iuvs=False,
              start_date='2014-01-01',
              end_date='2020-01-01',
              update_prefs=False,
              only_update_prefs=False,
              local_dir=None,
              list_files=False,
              new_files=True,
              exclude_orbit_file=False,
              download_only=False,
              varformat=None,
              prefix='',
              suffix='',
              get_support_data=False):
    """
    This function downloads MAVEN data loads it into tplot variables, if applicable.
    """

    # 1. Download files

    maven_files = maven_filenames(filenames, instruments, level, insitu, iuvs, start_date, end_date, update_prefs,
                                  only_update_prefs, local_dir)
    if instruments != 'kp':
        ancillary_only=True
    else:
        ancillary_only = False

    if not isinstance(type, list):
        type = [type]

    # Keep track of what files are downloaded
    files_to_load = []

    for instr in maven_files.keys():
        if maven_files[instr]:
            s = maven_files[instr][0]
            data_dir = maven_files[instr][1]
            public = maven_files[instr][2]

            # Add to list of files to load
            for f in s:
                # Filter by type
                if type is not None and instr != 'kp':
                    file_type_match = False
                    desc = l2_regex.match(f).group("description")
                    for t in type:
                        if t in desc:
                            file_type_match = True
                    if not file_type_match:
                        continue

                # Check if the files are KP data
                if instr == 'kp':
                    full_path = create_dir_if_needed(f, data_dir, 'insitu')
                else:
                    full_path = create_dir_if_needed(f, data_dir, level)

                files_to_load.append(os.path.join(full_path, f))

            if list_files:
                for f in s:
                    print(f)
                return

            if new_files:
                if instr == 'kp':
                    s = get_new_files(s, data_dir, instr, 'insitu')
                else:
                    s = get_new_files(s, data_dir, instr, level)
            if len(s) == 0:
                continue
            print("Your request will download a total of: "+str(len(s))+" files for instrument "+str(instr))
            print('Would you like to proceed with the download? ')
            valid_response = False
            cancel = False
            while not valid_response:
                response = (input('(y/n) >  '))
                if response == 'y' or response == 'Y':
                    valid_response = True
                    cancel = False
                elif response == 'n' or response == 'N':
                    print('Cancelled download. Returning...')
                    valid_response = True
                    cancel = True
                else:
                    print('Invalid input.  Please answer with y or n.')

            if cancel:
                continue

            if not exclude_orbit_file:
                print("Before downloading data files, checking for updated orbit # file from naif.jpl.nasa.gov")
                print("")
                get_orbit_files()

            i = 0
            display_progress(i, len(s))
            for f in s:
                i = i+1
                if instr == 'kp':
                    full_path = create_dir_if_needed(f, data_dir, 'insitu')
                else:
                    full_path = create_dir_if_needed(f, data_dir, level)
                get_file_from_site(f, public, full_path)
                display_progress(i, len(s))



    # 2. Load files into tplot

    if files_to_load:
        # Flatten out downloaded files from list of lists of filenames
        if isinstance(files_to_load[0], list):
            files_to_load = [item for sublist in files_to_load for item in sublist]

        # Only load in files into tplot if we actually downloaded CDF files
        cdf_files = [f for f in files_to_load if '.cdf' in f]
        sts_files = [f for f in files_to_load if '.sts' in f]
        kp_files = [f for f in files_to_load if '.tab' in f]

        loaded_tplot_vars = []
        if not download_only:
            # Create tplot variables
            for f in cdf_files:
                desc = l2_regex.match(os.path.basename(f)).group("description")
                if desc is not '' and suffix == '':
                    loaded_tplot_vars.append(pytplot.cdf_to_tplot(f, varformat=varformat,
                                                                 get_support_data=get_support_data, prefix=prefix,
                                                                 suffix=desc, merge=True))
                else:
                    loaded_tplot_vars.append(pytplot.cdf_to_tplot(f, varformat=varformat,
                                                                  get_support_data=get_support_data, prefix=prefix,
                                                                  suffix=suffix, merge=True))
            for f in sts_files:
                desc = l2_regex.match(os.path.basename(f)).group("description")
                if desc is not '' and suffix == '':
                    loaded_tplot_vars.append(pytplot.sts_to_tplot(f, prefix=prefix,
                                                                      suffix=desc, merge=True))
                else:
                    loaded_tplot_vars.append(pytplot.sts_to_tplot(f, prefix=prefix,
                                                                  suffix=suffix, merge=True))

            loaded_tplot_vars.append(maven_kp_to_tplot(filename=kp_files, ancillary_only=True))
            flat_list = [item for sublist in loaded_tplot_vars for item in sublist]

            for tvar in flat_list:
                pytplot.link(tvar, "mvn_kp::spacecraft::altitude", link_type='alt')
                pytplot.link(tvar, "mvn_kp::spacecraft::mso_x", link_type='x')
                pytplot.link(tvar, "mvn_kp::spacecraft::mso_y", link_type='y')
                pytplot.link(tvar, "mvn_kp::spacecraft::mso_z", link_type='z')
                pytplot.link(tvar, "mvn_kp::spacecraft::geo_x", link_type='geo_x')
                pytplot.link(tvar, "mvn_kp::spacecraft::geo_y", link_type='geo_y')
                pytplot.link(tvar, "mvn_kp::spacecraft::geo_z", link_type='geo_z')
                pytplot.link(tvar, "mvn_kp::spacecraft::sub_sc_longitude", link_type='lon')
                pytplot.link(tvar, "mvn_kp::spacecraft::sub_sc_latitude", link_type='lat')

            return list(set(flat_list))
