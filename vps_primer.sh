#!/bin/bash

# Run this script first thing when you get your VPS. It assumes you're logged
# in as root and is necessary for the rest of the scripts to run.

# This should be the only task you execute as root, when the script finishes,
# you should logout and log back in with the user created by the script.

# USAGE
# 1. Make the script executable:
#     $ chmod +x vps_primer.sh
# 2. Run the script. The only argument is the user you want to create.
#     $ ./vps_primer.sh webapps
#     (runs the script and creates a user "webapps")

# Simple function to colorize output
# http://stackoverflow.com/a/23006365/1330003
function echolor() {
    local exp=$1;
    local color=$2;
    if ! [[ $color =~ '^[0-9]$' ]] ; then
        case $(echo $color | tr '[:upper:]' '[:lower:]') in
            black) color=0 ;;
            red) color=1 ;;
            green) color=2 ;;
            yellow) color=3 ;;
            blue) color=4 ;;
            magenta) color=5 ;;
            cyan) color=6 ;;
            white|*) color=7 ;; # white or invalid color
        esac
    fi
    tput bold;
    tput setaf $color;
    echo $exp;
    tput sgr0;
}

# THE SCRIPT
# Not commenting much as all this stuff is self-explanatory
echolor "Setting up locales." blue
# Non-english speaking users can add additional languages here
locale-gen en_US.UTF-8
update-locale en_US.UTF-8
echolor "Updating system packages. This may take a while." blue
apt-get update -q > /dev/null
apt-get upgrade -y -q > /dev/null
echolor "Installing 'nano' text editor." blue
apt-get install -y -q nano > /dev/null
echolor "Creating user $1 with sudo privileges." blue
adduser $1
usermod -G sudo $1
echolor "Disabling Root login via SSH." blue
sed -i "s:RootLogin yes:RootLogin no:" /etc/ssh/sshd_config
service ssh restart
echolor "Done. Log out and log in as $1 from now on." green
