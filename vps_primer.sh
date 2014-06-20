#!/bin/bash

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

echolor "Setting up locales." blue
locale-gen en_US.UTF-8 es_ES.UTF-8 es_US.UTF-8 es_SV.UTF-8
update-locale en_US.UTF-8
echolor "Updating system packages. This may take a while." blue
apt-get update -q > /dev/null
apt-get upgrade -y -q > /dev/null
echolor "Installing 'nano' text editor." blue
apt-get install -q nano > /dev/null
echolor "Creating user jerivas with sudo privileges." blue
adduser jerivas
usermod -G sudo jerivas
echolor "Disabling Root login." blue
sed -i "s:RootLogin yes:RootLogin no:" /etc/ssh/sshd_config
service ssh restart
echolor "Done. Log out and log in as jerivas from now on." blue
