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
  /* Outputs this toplevel is currently on, as advertised by
   * output_enter/output_leave. Raw wl_output pointers owned by the display. */
  GPtrArray *outputs;
};

struct _AppGroup {
  char *app_id;
  char *name;
  char *icon;
  char *command;
  /* Additional identities from a pinned entry (desktop id without the
   * .desktop suffix, startup WM class). Used to merge running windows into
   * the pinned tile. */
  char *desktop_id;
  char *startup_wm_class;
  gboolean pinned;
  gboolean focused;
  gboolean seen;
  /* Pinned groups sort by settings order; unpinned groups by creation. */
  gint sort_index;
  GPtrArray *windows;
  ToplevelService *service;
};

typedef void (*ToplevelWindowListFunc)(gpointer data, AppGroup *group, GtkWidget *anchor);

ToplevelService *toplevel_service_new(PanelConfig *config,
    ToplevelWindowListFunc window_list, void (*changed_cb)(gpointer),
    gpointer data);
void toplevel_service_free(ToplevelService *service);
void toplevel_service_reload_pins(ToplevelService *service, PanelConfig *config);
GPtrArray *toplevel_service_groups(ToplevelService *service);
/* TRUE when the group has at least one window on output (or when output
 * information is still missing, so late metadata never hides a window).
 * Pinned groups are always visible on every output. */
gboolean toplevel_group_on_output(AppGroup *group, struct wl_output *output);

void toplevel_group_activate(AppGroup *group, GtkWidget *anchor);
void toplevel_group_middle(AppGroup *group, GtkWidget *anchor);
void toplevel_group_show_windows(AppGroup *group, GtkWidget *anchor);
void toplevel_window_activate(PanelToplevel *window);
void toplevel_window_minimize(PanelToplevel *window);
void toplevel_window_close(PanelToplevel *window);

#ifdef PANEL_TEST
ToplevelService *toplevel_service_new_for_test(void);
void toplevel_service_test_set_config(ToplevelService *service, PanelConfig *config);
void toplevel_service_test_rebuild(ToplevelService *service);
PanelToplevel *toplevel_service_test_add_window(ToplevelService *service,
    const char *app_id, const char *title, gboolean activated);
void toplevel_service_test_set_window_title(PanelToplevel *window, const char *title);
void toplevel_service_test_set_window_activated(PanelToplevel *window,
    gboolean activated);
void toplevel_service_test_add_window_output(PanelToplevel *window,
    struct wl_output *output);
void toplevel_service_test_close_window(PanelToplevel *window);
guint toplevel_service_test_group_count(ToplevelService *service);
AppGroup *toplevel_service_test_group_at(ToplevelService *service, guint index);
#endif
