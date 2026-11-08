project('adwaita-lite-panel', 'c',
  version: '0.2.0',
  license: 'GPL-3.0-or-later',
  default_options: ['c_std=c11', 'warning_level=3', 'werror=false'],
)

gtk4 = dependency('gtk4', version: '>= 4.10')
layer_shell = dependency('gtk4-layer-shell-0')
json_glib = dependency('json-glib-1.0')
pulse_glib = dependency('libpulse-mainloop-glib')
wayland_client = dependency('wayland-client')

wayland_scanner = find_program('wayland-scanner')
protocol_xml = files('protocols/wlr-foreign-toplevel-management-unstable-v1.xml')
protocol_header = custom_target('wlr-foreign-toplevel-client-header',
  input: protocol_xml,
  output: 'wlr-foreign-toplevel-management-unstable-v1-client-protocol.h',
  command: [wayland_scanner, 'client-header', '@INPUT@', '@OUTPUT@'],
)
protocol_code = custom_target('wlr-foreign-toplevel-private-code',
  input: protocol_xml,
  output: 'wlr-foreign-toplevel-management-unstable-v1-protocol.c',
  command: [wayland_scanner, 'private-code', '@INPUT@', '@OUTPUT@'],
)

sources = files(
  'src/audio.c',
  'src/config.c',
  'src/main.c',
  'src/shelf.c',
  'src/status.c',
  'src/theme.c',
  'src/toplevel.c',
)

executable('adwaita-lite-panel', sources, protocol_code, protocol_header,
  include_directories: include_directories('.'),
  dependencies: [gtk4, layer_shell, json_glib, wayland_client, pulse_glib],
  install: true,
)

audio_test = executable('test-audio',
  files('tests/test_audio.c', 'src/audio.c'),
  include_directories: include_directories('src'),
  dependencies: [pulse_glib],
)
test('audio-helpers', audio_test)
