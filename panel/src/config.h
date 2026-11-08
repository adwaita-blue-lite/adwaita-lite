/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include <glib.h>

typedef struct {
  char *name;
  char *command;
  char *icon;
  char *app_id;
  char *desktop_id;
  char *startup_wm_class;
} PinnedApp;

typedef struct {
  char *edge;
  char *density;
  char *theme;
  char *accent;
  int font_size;
  gboolean high_contrast;
  gboolean reduce_motion;
  gboolean clock_24h;
  gboolean panel_twilight;
  gboolean panel_network;
  GPtrArray *pinned;
} PanelConfig;

PanelConfig *panel_config_load(void);
PanelConfig *panel_config_load_defaults(void);
void panel_config_free(PanelConfig *config);
const char *panel_config_edge(const PanelConfig *config);
gboolean panel_config_vertical(const PanelConfig *config);
gboolean panel_config_compact(const PanelConfig *config);
gboolean panel_config_dark(const PanelConfig *config);
