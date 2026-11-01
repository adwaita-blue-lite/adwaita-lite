# vim: set ft=make :

alias upgrade := update

# Update system image, Flatpaks, containers, and other supported subsystems.
[group("system")]
update:
    #!/usr/bin/bash
    set -euo pipefail

    # Run uupd in the foreground for manual updates. The timer/service uses
    # JSON logs for journald, but `ujust update` should show interactive CLI
    # progress so users can see what is being updated.
    sudo uupd --hw-check=false

alias changelog := changelogs

# Show the changelog.
[group("system")]
changelogs:
    rpm-ostree db diff --changelogs

# Update device firmware.
[group("system")]
[no-exit-message]
update-firmware:
    fwupdmgr refresh --force
    fwupdmgr get-updates
    fwupdmgr update

alias auto-update := toggle-updates

# Turn automatic updates on or off.
[group("system")]
toggle-updates ACTION="prompt":
    #!/usr/bin/bash
    set -euo pipefail
    source /usr/lib/ujust/ujust.sh

    CURRENT_STATE="Disabled"
    if systemctl -q is-enabled uupd.timer; then
        CURRENT_STATE="Enabled"
    fi

    OPTION={{ ACTION }}
    if [ "$OPTION" == "prompt" ]; then
        echo "Automatic updates are currently: ${bold}${CURRENT_STATE}${normal}"
        echo "Enable or Disable automatic updates?"
        OPTION=$(ugum choose Enable Disable)
    elif [ "$OPTION" == "help" ]; then
        echo "Usage: ujust toggle-updates <enable|disable>"
        exit 0
    fi

    if [ "${OPTION,,}" == "enable" ]; then
        sudo systemctl enable --now uupd.timer
        sudo systemctl disable --now rpm-ostreed-automatic.timer flatpak-system-update.timer 2>/dev/null || true
        systemctl disable --now --user flatpak-user-update.timer 2>/dev/null || true
    elif [ "${OPTION,,}" == "disable" ]; then
        sudo systemctl disable --now uupd.timer
    fi
