# DX Stream Payload Design

## Purpose

Adwaita-Lite now has branch and tag plumbing for `main`, `dx`, `testing`, and `beta`, but the downstream branch contents still need to diverge intentionally. The first useful `dx` and `testing` images should carry the developer payload expected from Universal Blue DX streams, while `main` stays lean for low-memory consumer targets and `beta` remains a main-based compatibility canary for the next Fedora/rawhide-style base.

## Stream Contents

`main` remains the stable consumer image. It continues to remove Distrobox and its `ujust` recipe so low-memory systems do not expose container workflows that are not intended for the default install.

`dx` is the stable developer image. It should match the extras Bluefin DX ships relative to mainline Bluefin as closely as practical for Adwaita-Lite. The initial DX payload should include:

- Distrobox retained from the Universal Blue base image, including its `ujust` recipe.
- Homebrew support via the upstream Universal Blue `brew` image/files pattern used by Bluefin.
- Container and virtualization tooling from Bluefin DX, including Docker, containerd, Docker compose/buildx/model plugins, libvirt, QEMU, virt-manager, Cockpit, podman tooling, Incus/LXC, and related SELinux/support packages.
- Developer and debugging utilities from Bluefin DX, including flatpak-builder, git subtree/SVN helpers, Android tools, tracing/performance tools, qemu-user helpers, p7zip, and VS Code.
- DX service defaults from Bluefin DX where they apply to Adwaita-Lite, including enabling Docker and Podman sockets and required virtualization/group setup services.

`testing` is created from `dx` and initially carries the same payload. It exists so future WIP changes can ride on top of DX without affecting stable DX users. The first testing image may be equivalent to the first DX image.

`beta` remains based on `main`, not `dx`. It should receive the current stable payload and workflow fixes, but its only stream-specific behavior is building from `ghcr.io/ublue-os/base-main:beta` and publishing the `beta` tag family.

## Branch Update Plan

The implementation should update the branch contents, not just trigger empty workflow dispatches:

1. Update `dx` from current `main` so it includes the latest workflow and Containerfile fixes.
2. Apply the DX payload changes on `dx`.
3. Push `dx` and observe the `dx` image build.
4. Update `testing` from `dx` so it inherits the DX payload.
5. Push `testing` and observe the `testing` image build.
6. Update `beta` from current `main` without DX payload changes.
7. Push `beta` and observe the `beta` image build against the Universal Blue beta base.

## Implementation Boundaries

The first pass should avoid inventing Adwaita-Lite-only developer behavior. Prefer upstream Bluefin DX package lists, repo setup, service enables, tests, and file overlays where they are compatible with Adwaita-Lite. If a Bluefin DX item is GNOME-specific, hardware-specific, or too heavyweight for the goal, document why it is excluded instead of silently omitting it.

The DX payload should be branch-local for now. `main` should not gain stream-mode build arguments or conditional package logic during this pass unless implementation reveals that branch-local changes are unmaintainable.

## Validation

Local validation should include static tests proving the intended stream split where the files are changed:

- `main` removes Distrobox and does not install DX packages.
- `dx` retains Distrobox and includes the Bluefin DX package/service contract.
- `testing` is updated from `dx`, so its branch contents should match the DX contract until WIP testing-only changes are introduced.
- `beta` remains main-based and uses the beta base image.

Remote validation should observe successful GitHub Actions image builds for `dx`, `testing`, and `beta`. The `beta` build is especially important as a rawhide/next-Fedora compatibility signal. If it fails, investigation should determine whether the failure is caused by Adwaita-Lite payload assumptions or upstream beta base changes before making fixes.

## Out Of Scope

- Adding WIP-only testing changes beyond inheriting DX.
- Automatically promoting testing changes back to `dx` or `main`.
- Adding DX payload to `main` or `beta`.
- Replacing the branch-based stream model with a single-branch stream-mode build architecture.
