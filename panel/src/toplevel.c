/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "toplevel.h"

#include <gdk/wayland/gdkwayland.h>
#include <string.h>
#include <wayland-client.h>

#include "wlr-foreign-toplevel-management-unstable-v1-client-protocol.h"

struct _ToplevelService {
  struct wl_display *display;
  struct wl_registry *registry;
  struct wl_seat *seat;
  struct zwlr_foreign_toplevel_manager_v1 *manager;
  GPtrArray *windows;
  GPtrArray *groups;
  PanelConfig *config;
  ToplevelWindowListFunc window_list;
  gpointer window_list_data;
  void (*changed_cb)(gpointer);
  gpointer changed_data;
};

static void rebuild_groups(ToplevelService *service);
static void changed(ToplevelService *service);

static void changed(ToplevelService *service) {
  if (!service) return;
  rebuild_groups(service);
  if (service->changed_cb) service->changed_cb(service->changed_data);
}

static char *pin_app_id(const PinnedApp *pin) {
  if (pin->app_id && pin->app_id[0]) return g_strdup(pin->app_id);
  if (pin->desktop_id && pin->desktop_id[0]) {
    char *id = g_strdup(pin->desktop_id);
    size_t len = strlen(id);
    if (len > 8 && g_strcmp0(id + len - 8, ".desktop") == 0) id[len - 8] = '\0';
    return id;
  }
  return g_strdup(pin->name ? pin->name : "pinned");
}

static void toplevel_free(PanelToplevel *window) {
  if (!window) return;
  if (window->handle) zwlr_foreign_toplevel_handle_v1_destroy(window->handle);
  g_free(window->app_id);
  g_free(window->title);
  g_free(window);
}

static void group_free(AppGroup *group) {
  if (!group) return;
  g_free(group->app_id);
  g_free(group->name);
  g_free(group->icon);
  g_free(group->command);
  g_ptr_array_unref(group->windows);
  g_free(group);
}

static AppGroup *find_group(ToplevelService *service, const char *app_id,
    gboolean pinned) {
  for (guint i = 0; i < service->groups->len; i++) {
    AppGroup *group = g_ptr_array_index(service->groups, i);
    if (group->pinned == pinned && g_strcmp0(group->app_id, app_id) == 0)
      return group;
  }
  return NULL;
}

static AppGroup *ensure_group(ToplevelService *service, const char *app_id,
    gboolean pinned) {
  AppGroup *group = find_group(service, app_id, pinned);
  if (group) return group;
  group = g_new0(AppGroup, 1);
  group->app_id = g_strdup(app_id);
  group->name = g_strdup(app_id);
  group->icon = g_strdup(app_id);
  group->pinned = pinned;
  group->windows = g_ptr_array_new();
  group->service = service;
  g_ptr_array_add(service->groups, group);
  return group;
}

static void rebuild_groups(ToplevelService *service) {
  for (guint i = 0; i < service->groups->len; i++) {
    AppGroup *group = g_ptr_array_index(service->groups, i);
    g_ptr_array_set_size(group->windows, 0);
    group->focused = FALSE;
    group->pinned = FALSE;
    group->seen = FALSE;
  }

  if (service->config && service->config->pinned) {
    for (guint i = 0; i < service->config->pinned->len; i++) {
      PinnedApp *pin = g_ptr_array_index(service->config->pinned, i);
      char *id = pin_app_id(pin);
      AppGroup *group = ensure_group(service, id, TRUE);
      g_free(group->name);
      group->name = g_strdup(pin->name && pin->name[0] ? pin->name : id);
      g_free(group->icon);
      group->icon = g_strdup(pin->icon && pin->icon[0] ? pin->icon : "application-x-executable");
      g_free(group->command);
      group->command = g_strdup(pin->command);
      group->pinned = TRUE;
      group->seen = TRUE;
      g_free(id);
    }
  }

  for (guint i = 0; i < service->windows->len; i++) {
    PanelToplevel *window = g_ptr_array_index(service->windows, i);
    const char *app_id = window->app_id && window->app_id[0] ? window->app_id :
        (window->title && window->title[0] ? window->title : "window");
    AppGroup *group = find_group(service, app_id, TRUE);
    if (!group) group = ensure_group(service, app_id, FALSE);
    g_ptr_array_add(group->windows, window);
    group->seen = TRUE;
    if (window->activated) group->focused = TRUE;
    if (!group->pinned) {
      g_free(group->name);
      group->name = g_strdup(app_id);
      g_free(group->icon);
      group->icon = g_strdup(app_id);
    }
  }

  for (gint i = (gint)service->groups->len - 1; i >= 0; i--) {
    AppGroup *group = g_ptr_array_index(service->groups, (guint)i);
    if (!group->seen) {
      g_ptr_array_remove_index(service->groups, (guint)i);
    }
  }
}

static void handle_title(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle,
    const char *title) {
  (void)handle;
  PanelToplevel *window = data;
  g_free(window->title);
  window->title = g_strdup(title ? title : "");
  changed(window->service);
}

static void handle_app_id(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle,
    const char *app_id) {
  (void)handle;
  PanelToplevel *window = data;
  g_free(window->app_id);
  window->app_id = g_strdup(app_id ? app_id : "");
  changed(window->service);
}

static void handle_output_enter(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle,
    struct wl_output *output) {
  (void)data; (void)handle; (void)output;
}

static void handle_output_leave(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle,
    struct wl_output *output) {
  (void)data; (void)handle; (void)output;
}

static void handle_state(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle,
    struct wl_array *state) {
  (void)handle;
  PanelToplevel *window = data;
  window->activated = FALSE;
  window->minimized = FALSE;
  uint32_t *value;
  wl_array_for_each(value, state) {
    if (*value == ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_ACTIVATED) window->activated = TRUE;
    if (*value == ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_MINIMIZED) window->minimized = TRUE;
  }
  changed(window->service);
}

static void handle_done(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle) {
  (void)handle;
  PanelToplevel *window = data;
  changed(window->service);
}

static void handle_closed(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle) {
  (void)handle;
  PanelToplevel *window = data;
  ToplevelService *service = window->service;
  for (guint i = 0; i < service->windows->len; i++) {
    if (g_ptr_array_index(service->windows, i) == window) {
      g_ptr_array_remove_index(service->windows, i);
      break;
    }
  }
  window->handle = NULL;
  toplevel_free(window);
  changed(service);
}

static void handle_parent(void *data, struct zwlr_foreign_toplevel_handle_v1 *handle,
    struct zwlr_foreign_toplevel_handle_v1 *parent) {
  (void)data; (void)handle; (void)parent;
}

static const struct zwlr_foreign_toplevel_handle_v1_listener handle_listener = {
  .title = handle_title,
  .app_id = handle_app_id,
  .output_enter = handle_output_enter,
  .output_leave = handle_output_leave,
  .state = handle_state,
  .done = handle_done,
  .closed = handle_closed,
  .parent = handle_parent,
};

static void manager_toplevel(void *data, struct zwlr_foreign_toplevel_manager_v1 *manager,
    struct zwlr_foreign_toplevel_handle_v1 *handle) {
  (void)manager;
  ToplevelService *service = data;
  PanelToplevel *window = g_new0(PanelToplevel, 1);
  window->handle = handle;
  window->app_id = g_strdup("");
  window->title = g_strdup("");
  window->service = service;
  g_ptr_array_add(service->windows, window);
  zwlr_foreign_toplevel_handle_v1_add_listener(handle, &handle_listener, window);
}

static void manager_finished(void *data, struct zwlr_foreign_toplevel_manager_v1 *manager) {
  (void)data;
  zwlr_foreign_toplevel_manager_v1_destroy(manager);
}

static const struct zwlr_foreign_toplevel_manager_v1_listener manager_listener = {
  .toplevel = manager_toplevel,
  .finished = manager_finished,
};

static void registry_global(void *data, struct wl_registry *registry, uint32_t name,
    const char *interface, uint32_t version) {
  ToplevelService *service = data;
  if (strcmp(interface, zwlr_foreign_toplevel_manager_v1_interface.name) == 0) {
    service->manager = wl_registry_bind(registry, name,
        &zwlr_foreign_toplevel_manager_v1_interface, version < 3 ? version : 3);
    zwlr_foreign_toplevel_manager_v1_add_listener(service->manager, &manager_listener, service);
  } else if (strcmp(interface, wl_seat_interface.name) == 0) {
    service->seat = wl_registry_bind(registry, name, &wl_seat_interface, version < 7 ? version : 7);
  }
}

static void registry_remove(void *data, struct wl_registry *registry, uint32_t name) {
  (void)data; (void)registry; (void)name;
}

static const struct wl_registry_listener registry_listener = {
  .global = registry_global,
  .global_remove = registry_remove,
};

ToplevelService *toplevel_service_new(PanelConfig *config,
    ToplevelWindowListFunc window_list, void (*changed_cb)(gpointer),
    gpointer data) {
  GdkDisplay *gdk_display = gdk_display_get_default();
  if (!GDK_IS_WAYLAND_DISPLAY(gdk_display)) return NULL;
  ToplevelService *service = g_new0(ToplevelService, 1);
  service->display = gdk_wayland_display_get_wl_display(GDK_WAYLAND_DISPLAY(gdk_display));
  service->config = config;
  service->window_list = window_list;
  service->window_list_data = data;
  service->changed_cb = changed_cb;
  service->changed_data = data;
  service->windows = g_ptr_array_new_with_free_func((GDestroyNotify)toplevel_free);
  service->groups = g_ptr_array_new_with_free_func((GDestroyNotify)group_free);
  service->registry = wl_display_get_registry(service->display);
  wl_registry_add_listener(service->registry, &registry_listener, service);
  wl_display_roundtrip(service->display);
  wl_display_roundtrip(service->display);
  return service;
}

void toplevel_service_reload_pins(ToplevelService *service, PanelConfig *config) {
  if (!service) return;
  service->config = config;
  rebuild_groups(service);
  changed(service);
}

GPtrArray *toplevel_service_groups(ToplevelService *service) {
  return service ? service->groups : NULL;
}

void toplevel_window_activate(PanelToplevel *window) {
  if (window && window->handle && window->service->seat) {
    zwlr_foreign_toplevel_handle_v1_activate(window->handle, window->service->seat);
    wl_display_flush(window->service->display);
  }
}

void toplevel_window_minimize(PanelToplevel *window) {
  if (window && window->handle) {
    zwlr_foreign_toplevel_handle_v1_set_minimized(window->handle);
    wl_display_flush(window->service->display);
  }
}

void toplevel_window_close(PanelToplevel *window) {
  if (window && window->handle) {
    zwlr_foreign_toplevel_handle_v1_close(window->handle);
    wl_display_flush(window->service->display);
  }
}

void toplevel_group_activate(AppGroup *group) {
  if (!group) return;
  if (group->pinned && group->windows->len == 0) {
    if (group->command && group->command[0]) {
      GError *error = NULL;
      if (!g_spawn_command_line_async(group->command, &error)) {
        g_warning("panel: could not launch %s: %s", group->command,
            error ? error->message : "unknown");
        g_clear_error(&error);
      }
    }
    return;
  }
  if (group->windows->len == 1) {
    PanelToplevel *window = g_ptr_array_index(group->windows, 0);
    if (window->activated) toplevel_window_minimize(window);
    else toplevel_window_activate(window);
    return;
  }
  if (group->windows->len > 1 && group->service->window_list)
    group->service->window_list(group->service->window_list_data, group);
}

void toplevel_group_show_windows(AppGroup *group) {
  if (group && group->windows->len > 1 && group->service->window_list)
    group->service->window_list(group->service->window_list_data, group);
}

void toplevel_group_middle(AppGroup *group) {
  if (!group) return;
  if (group->windows->len == 1) {
    toplevel_window_close(g_ptr_array_index(group->windows, 0));
  } else if (group->windows->len > 1 && group->service->window_list) {
    group->service->window_list(group->service->window_list_data, group);
  }
}

void toplevel_service_free(ToplevelService *service) {
  if (!service) return;
  if (service->manager) zwlr_foreign_toplevel_manager_v1_destroy(service->manager);
  if (service->registry) wl_registry_destroy(service->registry);
  g_ptr_array_unref(service->windows);
  g_ptr_array_unref(service->groups);
  g_free(service);
}
