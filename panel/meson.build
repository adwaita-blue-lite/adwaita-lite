project('adwaita-lite-panel', 'c',
  version: '0.1.0',
  license: 'GPL-3.0-or-later',
  default_options: ['c_std=c11', 'warning_level=3', 'werror=false'],
)

gtk4 = dependency('gtk4', version: '>= 4.10')
layer_shell = dependency('gtk4-layer-shell-0')
json_glib = dependency('json-glib-1.0')

sources = files(
  'src/config.c',
  'src/main.c',
  'src/shelf.c',
  'src/theme.c',
)

executable('adwaita-lite-panel', sources,
  dependencies: [gtk4, layer_shell, json_glib],
  install: true,
)
