/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include <gtk/gtk.h>

#include "config.h"

struct zwlr_foreign_toplevel_handle_v1;
struct wl_output;

typedef struct _ToplevelService ToplevelService;
typedef struct _PanelToplevel PanelToplevel;
typedef struct _AppGroup AppGroup;

struct _PanelToplevel {
  struct zwlr_foreign_toplevel_handle_v1 *handle;
  ToplevelService *service;
  char *app_id;
  char *title;
  gboolean activated;
  gboolean minimized;
};

struct _AppGroup {
  char *app_id;
  char *name;
  char *icon;
  char *command;
  gboolean pinned;
  gboolean focused;
  gboolean seen;
  GPtrArray *windows;
  ToplevelService *service;
};

typedef void (*ToplevelWindowListFunc)(gpointer data, AppGroup *group);

ToplevelService *toplevel_service_new(PanelConfig *config,
    ToplevelWindowListFunc window_list, void (*changed_cb)(gpointer),
    gpointer data);
void toplevel_service_free(ToplevelService *service);
void toplevel_service_reload_pins(ToplevelService *service, PanelConfig *config);
GPtrArray *toplevel_service_groups(ToplevelService *service);

void toplevel_group_activate(AppGroup *group);
void toplevel_group_middle(AppGroup *group);
void toplevel_group_show_windows(AppGroup *group);
void toplevel_window_activate(PanelToplevel *window);
void toplevel_window_minimize(PanelToplevel *window);
void toplevel_window_close(PanelToplevel *window);
