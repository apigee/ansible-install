#!/usr/bin/python

# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ansible.module_utils.basic import AnsibleModule


class NamedObject(object):

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '<{0} {1}>'.format(self.__class__.__name__, self)

    def __str__(self):
        return self.name


class Planet(NamedObject):

    def __init__(self, name=''):
        self.regions = []
        super(self.__class__, self).__init__(name)

    @property
    def hosts(self):
        hosts = []
        for region in self.regions:
            hosts += region.hosts
        return hosts

    def get_host(self, name):
        hosts = [host for host in self.hosts if host.name == name]
        if hosts:
            return hosts[0]
        else:
            return None

    def get_services(self, name):
        services = []
        for region in self.regions:
            services += region.get_services(name)
        return services


class Region(NamedObject):

    def __init__(self, planet, name):
        self.planet = planet
        planet.regions.append(self)
        self.name = name
        self.number = int(name.split('-')[-1])
        self.hosts = []
        super(self.__class__, self).__init__(name)

    def get_services(self, name):
        services = []
        for host in self.hosts:
            services += host.get_services(name)
        return services


class Host(object):

    def __init__(self, region, name):
        self.region = region
        region.hosts.append(self)
        self.name = name
        self.services = []

    def get_services(self, name):
        services = []
        for service in self.services:
            if service.__class__.__name__ == name:
                services.append(service)
        return services

    def __repr__(self):
        return '<{0} {1}>'.format(self.__class__.__name__, self)

    def __str__(self):
        return self.name


class Service(object):

    def __init__(self, host):
        self.host = host
        host.services.append(self)

    @property
    def local_peers(self):
        peers = []
        for service in self.host.region.get_services(self.__class__.__name__):
            if service is not self:
                peers.append(service)
        return peers

    @property
    def global_peers(self):
        peers = []
        for service in self.host.region.planet.get_services(self.__class__.__name__):
            if service is not self:
                peers.append(service)
        return peers

    def __repr__(self):
        return '<{0} {1}>'.format(self.__class__.__name__, self)

    def __str__(self):
        return self.host.name


class Cassandra(Service):

    def __str__(self):
        return '{0}:{1},1'.format(self.host.name, self.host.region.number)


class ZooKeeper(Service):

    def __init__(self, host, observer=False):
        self.observer = observer
        super(self.__class__, self).__init__(host)

    def __str__(self):
        return self.host.name + ':observer' if self.observer else ''


class OpenLDAP(Service):

    @property
    def replicates(self):
        return bool(self.local_peers) or bool(self.global_peers)


class ManagementServer(Service): pass
class EnterpriseUI(Service): pass
class Router(Service): pass
class MessageProcessor(Service): pass
class Qpidd(Service): pass
class QpidServer(Service): pass
class PostgreSQL(Service): pass
class PostgresServer(Service): pass
class DevPortalNginx(Service): pass
class DevPortalPostgreSQL(Service): pass


profile_map = dict(
    ds = [Cassandra, ZooKeeper],
    ld = [OpenLDAP],
    ms = [OpenLDAP, ManagementServer, EnterpriseUI],
    r = [Router],
    mp = [MessageProcessor],
    rmp = [Router, MessageProcessor],
    qs = [Qpidd, QpidServer],
    ps = [PostgreSQL, PostgresServer],
    sa = [Cassandra, ZooKeeper, OpenLDAP, ManagementServer, EnterpriseUI, Router, MessageProcessor],
    sax = [Qpidd, QpidServer, PostgreSQL, PostgresServer],
    aio = [Cassandra, ZooKeeper, OpenLDAP, ManagementServer, EnterpriseUI, Router, MessageProcessor, Qpidd, QpidServer, PostgreSQL, PostgresServer],
    pdb = [DevPortalPostgreSQL],
    dp = [DevPortalNginx]
)


def parse_topology(topology):
    parsed_topology = {}
    for entry in topology:
        region, host, profiles = entry.strip().split()
        profiles = profiles.split(',')
        if region not in parsed_topology:
            parsed_topology[region] = []
        # This somewhat awkward structure is due to the requirement that
        # order is preserved in the host list. This matters for certain
        # service types like Cassandra, Zookeeper, and the management server.
        parsed_topology[region].append((host, profiles))
    return parsed_topology


def build_planet(parsed_topology):
    planet = Planet()
    for region_name in sorted(parsed_topology):
        region = Region(planet, region_name)
        for hostname, profiles in parsed_topology[region.name]:
            host = Host(region, hostname)
            for profile in profiles:
                for service in profile_map[profile]:
                    service(host)
    return planet


def get_pg_info(pgsqls, hostvars):
    master = ''
    standby = []
    trust = ''
    if len(pgsqls) > 0:
        master = hostvars[pgsqls[0].host.name]['ansible_default_ipv4']['address']
    if master:
        if len(pgsqls) > 1:
            trust += 'conf_pg_hba_replication.connection='
        for pgsql in pgsqls:
            address = hostvars[pgsql.host.name]['ansible_default_ipv4']['address']
            if address != master:
                standby.append(address)
                trust += 'host    replication     apigee        {0}/32            trust\\n'.format(
                    address )
        trust = trust.rstrip('\\n')
    return master, standby, trust


def get_apigee_facts(hostvars, topology, my_hostname):
    facts = {}
    parsed_topology = parse_topology(topology)
    planet = build_planet(parsed_topology)

    me = planet.get_host(my_hostname)
    # Bail out if this host is not a part of the planet.
    if not me:
        return dict(apigee=facts)
    # Find and save the list of profiles for this host.
    for region, hosts in parsed_topology.items():
        if region == me.region.name:
            for host, profiles in hosts:
                if host == me.name:
                    facts['profiles'] = profiles

    ### OpenLDAP ###

    ldap_services = planet.get_services('OpenLDAP')
    ldap_hosts = [service.host for service in ldap_services]
    ldap_replication = len(ldap_services) > 1

    if me in ldap_hosts:
        if not ldap_replication:
            facts['ldap_type'] = '1'
        else:
            facts['ldap_type'] = '2'
            try:
                facts['ldap_sid'] = ldap_hosts.index(me) + 1
            except ValueError:
                facts['ldap_sid'] = 1
            ldap_primary = ldap_hosts[0]
            # The primary LDAP service should look at the secondary LDAP service for replication.
            # All other hosts should look at the primary. In the case of more than two LDAP
            # service, this is temporary until full mesh replication is enabled.
            if ldap_primary is me:
                peer = ldap_hosts[1].name
            else:
                peer = ldap_primary.name
            facts['ldap_peer'] = hostvars[peer]['ansible_default_ipv4']['address']

    ### Management server ###

    # Calculate the pause value for each management host to avoid race conditions.
    ms_hosts = [service.host for service in planet.get_services('ManagementServer')]
    if me in ms_hosts:
        index = ms_hosts.index(me)
        pause = index * 15
        # If not the first management server, add a buffer so the first one can populate Cassandra.
        if index > 0:
            pause += 60
        facts['ms_pause'] = pause

        # If there is one standalone LDAP host in this region or the same number of standalone LDAP
        # hosts as management hosts, set up standalone LDAP.
        local_ldap_hosts = [service.host for service in me.region.get_services('OpenLDAP')]
        local_ms_hosts = [service.host for service in me.region.get_services('ManagementServer')]
        if len(local_ldap_hosts) == len(local_ms_hosts):
            facts['ldap_remote'] = False
            facts['ldap_host'] = ''
        elif len(local_ldap_hosts) == (len(local_ms_hosts) + 1):
            facts['ldap_remote'] = True
            ldap_host = [host.name for host in local_ldap_hosts if host not in local_ms_hosts][0]
            facts['ldap_host'] = hostvars[ldap_host]['ansible_default_ipv4']['address']
        elif len(local_ldap_hosts) == (len(local_ms_hosts) * 2):
            facts['ldap_remote'] = True
            local_ldap_only_hosts = [host.name for host in local_ldap_hosts if host not in local_ms_hosts]
            ldap_host = local_ldap_only_hosts[local_ms_hosts.index(me)]
            facts['ldap_host'] = hostvars[ldap_host]['ansible_default_ipv4']['address']
        else:
            raise Exception('Invalid number of ld profiles')

    # Use the first MS in this DC unless there is none. If none, use the first found.
    local_ms = me.region.get_services('ManagementServer')
    if local_ms:
        facts['msip'] = hostvars[local_ms[0].host.name]['ansible_default_ipv4']['address']
    else:
        facts['msip'] = hostvars[planet.get_services('ManagementServer')[0].host.name]['ansible_default_ipv4']['address']

    ### Miscellaneous ###

    # This can be the same across regions since pods with identical names in different regions are actually unique.
    facts['mp_pod'] = 'gateway'

    facts['region'] = me.region.name

    ### Cassandra ###

    # Calculate the pause value for each datastore host to avoid race conditions.
    cass_hosts = [service.host for service in planet.get_services('Cassandra')]
    if me in cass_hosts:
        facts['cass_pause'] = cass_hosts.index(me)* 15

    cass_hosts = []
    # Make sure our local region comes first.
    regions = [me.region] + [region for region in planet.regions if region != me.region]
    for region in regions:
        for cassandra in region.get_services('Cassandra'):
            cass_hosts.append('{0}:{1},1'.format(hostvars[cassandra.host.name]['ansible_default_ipv4']['address'], region.number))
    facts['cass_hosts'] = ' '.join(cass_hosts)

    ### ZooKeeper ###

    zk_hosts = []
    region_count = len(planet.regions)
    for region in planet.regions:
        # Simple observer selection algorithm: If the number of regions is greater than 1 and odd,
        # place one voter in each; if the number of regions is even, place two voters in the first
        # and one in the others.
        if (region_count % 2 == 1) or (region_count % 2 == 0 and region.number == 1):
            voters = 3
        else:
            voters = 2
        for zk in region.get_services('ZooKeeper'):
            if voters:
                name = hostvars[zk.host.name]['ansible_default_ipv4']['address']
                voters -= 1
            else:
                name = hostvars[zk.host.name]['ansible_default_ipv4']['address'] + ':observer'
            zk_hosts.append(name)
    facts['zk_hosts'] = ' '.join(zk_hosts)

    zk_client_hosts = []
    for zk in me.region.get_services('ZooKeeper'):
        zk_client_hosts.append(hostvars[zk.host.name]['ansible_default_ipv4']['address'])
    facts['zk_client_hosts'] = ' '.join(zk_client_hosts)

    ### PostgreSQL ###

    pgsqls = me.region.planet.get_services('PostgreSQL')

    #facts['pg_master'] = ''
    # If pg_master is defined as a variable, use the user-supplied value. Otherwise, use the first
    # PostgreSQL service found in any region.
    #if len(pgsqls) > 0:
    #    facts['pg_master'] = hostvars[pgsqls[0].host.name]['ansible_default_ipv4']['address']

    facts['pg_master'], facts['pg_standby'], facts['pg_trust'] = get_pg_info(pgsqls, hostvars)

    #facts['pg_trust'] = ''
    #facts['pg_standby'] = []
    #if facts['pg_master']:
    #    if len(pgsqls) > 1:
    #        facts['pg_trust'] += 'conf_pg_hba_replication.connection='
    #    for pgsql in pgsqls:
    #        if hostvars[pgsql.host.name]['ansible_default_ipv4']['address'] != facts['pg_master']:
    #            pg_standby = hostvars[pgsql.host.name]['ansible_default_ipv4']['address']
    #            facts['pg_standby'].append(pg_standby)
    #            facts['pg_trust'] += 'host    replication     apigee        {0}/32            trust\\n'.format(
    #                pg_standby )
    #    facts['pg_trust'] = facts['pg_trust'].rstrip('\\n')

    ### Developer Portal ###

    dp_pgsqls = me.region.planet.get_services('DevPortalPostgreSQL')
    facts['dp'] = {}

    if dp_pgsqls:
        facts['dp']['pg_master'], facts['dp']['pg_standby'], facts['dp']['pg_trust'] = get_pg_info(dp_pgsqls, hostvars)
    else:
        facts['dp']['pg_master'] = facts['pg_master']
        facts['dp']['pg_trust'] = facts['pg_trust']
        facts['dp']['pg_standby'] = facts['pg_standby']

        #facts['dp']['pg_master'] = ''
        #if len(dp_pgsqls) > 0:
        #    facts['dp']['pg_master'] = hostvars[dp_pgsqls[0].host.name]['ansible_default_ipv4']['address']

        #facts['dp']['pg_trust'] = ''
        #facts['dp']['pg_standby'] = []
        #if facts['dp']['pg_master']:
        #    if len(dp_pgsqls) > 1:
        #        facts['dp']['pg_trust'] += 'conf_pg_hba_replication.connection='
        #    for dp_pgsql in dp_pgsqls:
        #        if dp_pgsql.host.name != facts['dp']['pg_master']:
        #            facts['dp']['pg_standby'].append(dp_pgsql.host.name)
        #            facts['dp']['pg_trust'] += 'host    replication     apigee        {0}/32            trust\\n'.format(
        #                hostvars[dp_pgsql.host.name]['ansible_default_ipv4']['address'] )
        #    facts['dp']['pg_trust'] = facts['dp']['pg_trust'].rstrip('\\n')

    facts['dp']['pg_backend'] = ''

    if 'dp' in facts['profiles']:
        if 'pdb' in facts['profiles']:
            facts['dp']['pg_backend'] = hostvars[me.name]['ansible_default_ipv4']['address']
        else:
            local_dp_pgsqls = me.region.get_services('DevPortalPostgreSQL')
            local_pgsqls = me.region.get_services('PostgreSQL')
            if local_dp_pgsqls:
                facts['dp']['pg_backend'] = hostvars[local_dp_pgsqls[0].host.name]['ansible_default_ipv4']['address']
            elif dp_pgsqls:
                facts['dp']['pg_backend'] = hostvars[dp_pgsqls[0].host.name]['ansible_default_ipv4']['address']
            elif local_pgsqls:
                facts['dp']['pg_backend'] = hostvars[local_pgsqls[0].host.name]['ansible_default_ipv4']['address']
            elif pg_sqls:
                facts['dp']['pg_backend'] = hostvars[pgsqls[0].host.name]['ansible_default_ipv4']['address']

    return dict(apigee=facts)


def main():
    module = AnsibleModule(
        argument_spec = dict(
            hostvars = dict(required=True, type='dict'),
            topology = dict(required=True, type='list'),
            my_hostname = dict(required=True)
        )
    )
    try:
        hostvars = module.params['hostvars']
        topology = module.params['topology']
        my_hostname = module.params['my_hostname']
        apigee_facts = get_apigee_facts(hostvars, topology, my_hostname)
        module.exit_json(changed=False, ansible_facts=apigee_facts)
    except Exception as error:
        module.fail_json(msg=str(error))


if __name__ == '__main__':
    main()
