# Adwaita-Lite ujust recipes.
#
# Loaded automatically by the base image's ujust wrapper — any *.just
# under /usr/share/ublue-os/just/ is merged into the single `ujust`
# command. Recipes below can be invoked as `ujust <name>`.

# Show the currently-configured memory strategy + active swap devices.
swap-status:
    #!/usr/bin/env bash
    set -eu
    strategy=$(python3 -c "import json; print(json.load(open('/var/lib/adwaita-lite/install-config.json')).get('memory_strategy', 'zram'))" 2>/dev/null || echo 'zram (default)')
    echo "Configured strategy: $strategy"
    echo ""
    echo "Active swap devices:"
    swapon --show || echo "  (none)"

# Switch memory strategy between zram (in-memory compression) and zswap
# (zram + encrypted disk swap for overflow). The target user's wizard
# picks one at install; this lets you change your mind later. Requires

# a reboot to take effect.
toggle-swap:
    #!/usr/bin/env bash
    set -eu
    current=$(python3 -c "import json; print(json.load(open('/var/lib/adwaita-lite/install-config.json')).get('memory_strategy', 'zram'))" 2>/dev/null || echo "zram")
    if [ "$current" = "zram" ]; then
        next="zswap"
        desc="zswap-backed (adds a 4 GB encrypted disk swap for overflow when RAM + zram fills)"
    else
        next="zram"
        desc="zram-only (no disk swap; lighter on storage wear)"
    fi
    echo "Current memory strategy: $current"
    echo "Will switch to:          $next"
    echo "   $desc"
    echo ""
    read -rp "Proceed? [y/N] " yn
    case "$yn" in
        [Yy]*) ;;
        *) echo "Cancelled."; exit 0;;
    esac

    if [ "$next" = "zswap" ]; then
        read -rp "Swap file size in GB [4]: " size
        size=${size:-4}
        case "$size" in
            ''|*[!0-9]*)
                echo "Swap size must be a whole number from 1 to 256 GB." >&2
                exit 1
                ;;
        esac
        if [ "${#size}" -gt 3 ]; then
            echo "Swap size must be a whole number from 1 to 256 GB." >&2
            exit 1
        fi
        size=$((10#$size))
        if [ "$size" -lt 1 ] || [ "$size" -gt 256 ]; then
            echo "Swap size must be a whole number from 1 to 256 GB." >&2
            exit 1
        fi
        sudo /usr/libexec/adwaita-lite-set-memory-strategy zswap "$size"
    else
        sudo /usr/libexec/adwaita-lite-set-memory-strategy zram
    fi

    echo ""
    echo "A reboot is required for the change to take effect."
    read -rp "Reboot now? [y/N] " yn
    case "$yn" in
        [Yy]*) sudo systemctl reboot;;
        *) echo "Reboot later with: sudo systemctl reboot";;
    esac

# Alias matching Universal Blue docs.
devmode:
    @ujust toggle-devmode

# Toggle developer mode between the Adwaita-Lite :latest and :dx streams.
toggle-devmode:
    #!/usr/bin/env bash
    set -euo pipefail

    latest_ref="ghcr.io/adwaita-blue-lite/adwaita-lite:latest"
    dx_ref="ghcr.io/adwaita-blue-lite/adwaita-lite:dx"
    current_tag=$(jq -r '."image-tag" // ""' /usr/share/ublue-os/image-info.json 2>/dev/null || true)

    if [[ "$current_tag" == "dx" ]]; then
        gum confirm "Would you like to disable developer mode?" || exit 0
        echo "Rebasing to a non developer image"
        pkexec bootc switch --enforce-container-sigpolicy "$latest_ref"
        exit 0
    fi

    gum confirm "Would you like to enable developer mode?" || exit 0
    echo "Rebasing to a developer image"
    pkexec bootc switch --enforce-container-sigpolicy "$dx_ref"
    echo "Use ujust dx-group to add your user to the correct groups and complete the installation after rebooting into the development image"

# Configure docker, incus-admin, libvirt, and serial permissions for this user.
dx-group:
    #!/usr/bin/pkexec bash
    set -euo pipefail

    append_group() {
        local group_name="$1"
        if ! grep -q "^${group_name}:" /etc/group; then
            echo "Appending ${group_name} to /etc/group"
            grep "^${group_name}:" /usr/lib/group >> /etc/group
        fi
    }

    groups_add=(docker incus-admin libvirt dialout)

    for group_add in "${groups_add[@]}"; do
        append_group "$group_add"
        usermod -aG "$group_add" {{ `id -un` }}
    done

    echo "Reboot system and log back in to use docker, libvirt, incus, and serial connections."
# Launch the DX-only Goblin Mode easter egg.
goblin:
    /usr/bin/adwaita-lite-goblin
