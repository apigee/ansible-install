# What is it?

A set of lightweight roles and playbooks to manage the installation of Apigee
Edge, create an Apigee mirror, and start and stop Apigee Edge services.

This README will guide you through the basics of configuring an Ansible
environment and running the Apigee Edge build playbook. Many advanced options
are available for Ansible and the included roles that are outside of the scope
of this document; refer to <http://docs.ansible.com/> and examine the included
roles for complete information.

This is not an officially supported Google product.



# Alternative tools

These roles and playbooks provide the simplest possible interface to install an
Apigee planet using Ansible. They drive the installation using ideal defaults
and require just a few simple steps to perform a full installation. They do not
cover additional operational tasks you may wish to perform, such as
infrastructure creation, OS management, Apigee planet expansion, and other
tasks. If you are looking for an Ansible-managed solution for those tasks, see
the expanded Ansible roles offered at
<https://github.com/apigee/playbook-setup-ansible>.



# Quickstart

## Install Ansible

The Ansible installation method depends on your distribution.

To install on Debian or Ubuntu from the distributor repository:
`sudo apt install ansible`

To install on Red Hat or CentOS from the distributor repository:
`sudo yum -y install ansible`

To install from pip:
`sudo pip install ansible`

Full installation details including packages for the latest Ansible release
are available at <https://docs.ansible.com/ansible/latest/intro_installation.html>.

## Populate your Ansible inventory

Create a plain text file (e.g., `hosts-apigee-dev`):

```
[apigee]
host1
host2
host3
host4
host5
```

The file is in INI format; the first line creates a host group named `apigee`
and subsequent lines list all hosts in your Apigee planet.

Inventory details are at <https://docs.ansible.com/ansible/latest/intro_inventory.html>.

## Configure SSH access and test Ansible

In order for Ansible to function you will need direct SSH access to the hosts
you wish to control. Ansible uses the standard OpenSSH client to establish
connections, so any settings in your local OpenSSH configuration file, such as
custom usernames or private keys, are respected. You can also override SSH
configuration settings in Ansible playbooks or the command line.

The simplest test to verify Ansible connectivity is:

`ansible -i hosts-apigee-dev apigee -m ping`

This command uses the inventory file we created earlier, targets the `apigee`
host group, and executes the `ping` module on the remote hosts. Assuming all
goes well, you will receive output similar to this (truncated for brevity):

```
host1 | SUCCESS => {
    "changed": false,
    "failed": false,
    "ping": "pong"
}
host2 | SUCCESS => {
    "changed": false,
    "failed": false,
    "ping": "pong"
}
...
```

You can change the remote SSH user:

`ansible -i hosts-apigee-dev apigee -m ping -u otheruser`

Prompt for an SSH password:

`ansible -i hosts-apigee-dev apigee -m ping -k`

Elevate to root through sudo:

`ansible -i hosts-apigee-dev apigee -m ping --become`

Prompt for a sudo password:

`ansible -i hosts-apigee-dev apigee -m ping --become -K`

Many other options are available; see <https://docs.ansible.com/ansible/latest/intro_adhoc.html>
or `man ansible` for a full description.

## Edit the build playbook

Edit `apigee-build-planet.yml`. Inside, you will find a number of settings you
may wish to change. The `apigee_topology` variable and all variables with
a value of SET_ME are mandatory; all other settings are optional.

One of the most important variables is the `apigee_topology` variable, which
drives the execution of the Apigee roles to correctly configure each host with
the proper Apigee profiles. Each item in the list contains three space-separated
fields: the region name, the hostname, and a comma-separated list of Apigee
profiles. Note that the hostname in the second field must match the name of the
host as defined in your inventory including the domain name suffix, if
applicable. For a full list of valid profiles in the third field, see
<https://docs.apigee.com/private-cloud/latest/install-edge-components-node#specifyingthecomponentstoinstall>.

There are some additional variables that are usually necessary to correctly
deploy an Apigee cluster using Ansible:

- `apigee_repository_username`: The username provided by Apigee to access the
repository at software.apigee.com and the file transfer service at sftp.apigee.com.
- `apigee_repository_password`: The password provided by Apigee to access the
repository at software.apigee.com and the file transfer service at sftp.apigee.com.
- `apigee_license_path`: The path to the license file provided by Apigee for
on-premises deployment. If an absolute path, this may be located anywhere on the
local filesystem. If a bare filename, the license file must be copied to
`roles/apigee-edge/files`.
- `apigee_admin_email`: The email of the Apigee Edge admin user.
- `apigee_admin_password`: The password of the Apigee Edge admin user.
- `apigee_organization_name`: The name of the organization to create.
- `apigee_environment_name`: The name of the environment to create.
- `apigee_virtual_host_aliases`: A list of hostnames and/or addresses for the
default virtual host.

Many other optional variables exist; for a full list, look at the
defaults/main.yml file of each role. Additional playbook details are at
<https://docs.ansible.com/ansible/latest/playbooks.html>.

## Run the build playbook

With Ansible configured and apigee-build-planet.yml updated, you can run the
playbook to build your planet:

`ansible-playbook -i hosts-apigee-dev apigee-build-planet.yml`

If necessary, you may want to pass additional options to `ansible-playbook` in
order to specify the remote user or prompt for a password. Details of
`ansible-playbook` are at <https://docs.ansible.com/ansible/latest/ansible-playbook.html>.

If playbook execution fails, the output of `ansible-playbook` may be sufficient to
diagnose. If not, the `/tmp/setup-root.log` file on the remote host will provide
additional insight into the cause of the failure. Since the Apigee installer is
idempotent, it is safe to re-run `ansible-playbook` once the cause of the failure
is fixed. The only exception is if incorrect profiles are applied to some hosts
in the cluster. If you accidentally apply incorrect profiles (such as putting an
rmp profile on an ms host), you can clean up by removing all packages and the
installation directory on all Apigee hosts:

`sudo yum -y remove 'apigee-*' 'edge-*'; sudo rm -rf /opt/apigee`

Once cleanup is complete, run the `apigee-build.planet.yml` playbook again.



# Known Limitations

1) No support for more than two management servers. The management servers will
be set up, but replication will not (currently) be enabled between more than
two LDAP directories.

2) No support for standalone LDAP. You can install "ld" profiles, but management
servers will ignore them.

3) No support for monetization profiles. To enable monetization, build the planet
using Ansible then manually apply the `mo` profile to appropriate nodes.
