/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include <gtk/gtk.h>

#include "config.h"

typedef struct {
  gboolean visible;
  int percent;
  const char *icon;
  const char *tooltip;
  const char *label;
  int severity; /* 0 normal, 1 warning, 2 critical */
} PanelBatteryView;

typedef struct {
  gboolean visible;
  const char *icon;
  const char *tooltip;
  const char *label;
} PanelNetworkView;

typedef struct {
  gboolean visible;
  int percent;
  const char *tooltip;
} PanelBacklightView;

typedef struct _PanelStatus PanelStatus;

PanelStatus *panel_status_new(PanelConfig *config, void (*changed)(gpointer), gpointer data);
void panel_status_set_config(PanelStatus *status, PanelConfig *config);
void panel_status_free(PanelStatus *status);
void panel_status_get(PanelStatus *status, PanelBatteryView *battery,
    PanelNetworkView *network, PanelBacklightView *backlight);
