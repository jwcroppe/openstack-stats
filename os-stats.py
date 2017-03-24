# Copyright 2017 Joe Cropper
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import cli.app
import json
import os
import requests
import sys

STACKALYTICS_BASE_URL = "http://stackalytics.com"
CONTRIB_URL = "%s/api/1.0/contribution" % (STACKALYTICS_BASE_URL)

######################################################
##############  Contribution Routines  ###############
######################################################
def __get_contribution_for_user(user, release=None):
    """
    Retrieves Stackalytics-structured contribution data for the specified user.
    See http://stackalytics.readthedocs.org/en/latest/userdoc/api_v1.0.html.

    :param user: the user whose contribution data to pull (e.g., jwcroppe)
    :param release: the OpenStack release (e.g., juno, kilo, etc.) for which
                    stats should be pulled; if unspecified, the current release
                    is implicitly assumed (optional)
    :returns: a dictionary of the user's contribution data; see the API link
              above for details on structure of the returned dictionary
    """
    url = ("%s?user_id=%s" %
           (CONTRIB_URL, user))
    if release:
        url = "%s&project_type=openstack&release=%s" % (url, release)
    ret = None

    try:
        ret = requests.get(url).json()['contribution']
    except Exception:
        # Effectively assume the user didn't contribute anything.
        pass
    if ret:
        # Just sum up all the review (e.g., -1, +1, etc.) count totals.
        ret['marks'] = sum(ret['marks'].values())
    return ret


def __get_aggregate_contributions(contrib_list):
    """Aggregates contribution data from a list of contributions."""
    # Structure that is used for the aggregated contributions; this is [mostly]
    # a structural copy of what the Stackalytics API contractually promises.
    ret = dict(change_request_count=0,
               commit_count=0,
               completed_blueprint_count=0,
               drafted_blueprint_count=0,
               email_count=0,
               filed_bug_count=0,
               loc=0,
               # Just roll up all the review votes into a single count since
               # we're not really interested in vote-specific data [yet].
               marks=0,
               patch_set_count=0,
               resolved_bug_count=0,
               abandoned_change_requests_count=0,
               translations=0)

    # For each user's contributions, aggregate the contribution data.
    for contrib in contrib_list:
        # Loop through the stats (e.g., commit_count, email_count, etc.).
        for key in contrib:
            ret[key] = ret[key] + contrib[key]

    return ret


######################################################
#################  File Routines  ####################
######################################################
def __get_users_from_file(path, map_path=None):
    """
    This routine expects to be fed a path to a file containing a single
    line of comma-delimited email addresses, from which it will derive
    a list of users (e.g., xx@yy.com will result in 'xx').
    """
    def get_tokens(path):
        """Read the first line of a file and returns comma-delimited tokens."""
        tokens = None
        fn = None
        try:
            fn = os.path.join(os.path.dirname(__file__), path)
            with open(fn, "r") as file_stream:
                for line in file_stream:
                    tokens = line.split(",")
                    break
        except Exception as e:
            print("Error reading file `%s`: %s" % (fn, unicode(e)))
            sys.exit(1)
        return tokens

    def get_eff_user(user, map_path=None):
        """Returns the effective user name if a mapping is available."""
        if not map_path:
            # No mapping available; return the email prefix.
            return user
        user_map_list = get_tokens(map_path)
        # Create a dict of the form {email-prefix: gerrit-id}.
        user_map = dict((key.strip(), value.strip()) for (key, value) in
                        [x.split(':') for x in user_map_list])
        return user_map[user] if user in user_map else user

    emails = get_tokens(path)
    # Ensure we don't have duplicate entries.
    return list(set([get_eff_user(email[0:email.find('@')].strip(),
                                  map_path=map_path)
                     for email in emails]))


######################################################
################  Display Routines  ##################
######################################################
def __display_stats(contrib_data):
    """Common stat display method."""
    if contrib_data:
        print("Contributions:")
        print(json.dumps(contrib_data, indent=4, sort_keys=True))
    else:
        print("Could not find any OpenStack contribution data for that user.")


def __display_user_stats(user, release=None):
    """Prints contribution data for the user and optional release."""
    contrib_data = __get_contribution_for_user(user, release=release)
    __display_stats(contrib_data)


def __display_aggregate_stats(path, map_path=None, release=None):
    """Prints contribution data for all users and optional release."""
    users = __get_users_from_file(path, map_path=map_path)
    # Keep a record of users we couldn't find on review.openstack.org.
    unknown = []
    # Keep track of the contributions.
    contribs = []

    for user in users:
        contrib = __get_contribution_for_user(user, release=release)
        if not contrib:
            unknown.append(user)
        else:
            contribs.append(contrib)

    unknown.sort()
    print("----------------------------------------\n"
          "Users not found on review.openstack.org:\n"
          "----------------------------------------\n"
          "%s\n"
          "----------------------------------------" % ', '.join(unknown))
    __display_stats(__get_aggregate_contributions(contribs))


def __display_unexpected_input():
    """Prints an error message when unexpected input is received."""
    print("Unexpected input.")


######################################################
#############  CLI Application Setup  ################
######################################################
@cli.app.CommandLineApp
def os_stats(app):
    if app.params.user:
        __display_user_stats(app.params.user, release=app.params.release)
    elif app.params.file:
        __display_aggregate_stats(app.params.file,
                                  map_path=app.params.map_file,
                                  release=app.params.release)
    else:
        __display_unexpected_input()
    sys.exit(0)


os_stats.add_param("-u", "--user",
                   help="the user whose stats to show; this is the user's "
                        "Gerrit ID for review.openstack.org (takes "
                        "precedence over the --file parameter)",
                   default=None)
os_stats.add_param("-f", "--file",
                   help="a path to a file that contains a comma-delimited "
                        "set of email addresses (e.g., me@mycompany.com) for "
                        "which aggregated stats will be shown (if present, "
                        "duplicate entries will be auto-filtered from the "
                        "final results)",
                   default=None)
os_stats.add_param("-m", "--map-file",
                   help="a path to a file that contains a comma-delimited "
                        "set of `email-prefix:gerrit-id` mappings (e.g., "
                        "jane:jane-gerrit); this is needed for cases in "
                        "which the user's email prefix is not the same as "
                        "the user's Gerrit ID",
                   default=None)
os_stats.add_param("-r", "--release",
                   help="the OpenStack release (e.g., kilo) for which "
                        "stats will be queried; if left unspecified, "
                        "the default is the current release",
                   default=None)


if __name__ == "__main__":
    """The application's main entry point."""
    os_stats.run()
