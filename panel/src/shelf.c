/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "shelf.h"
#include "audio.h"
#include "status.h"

#include <gtk4-layer-shell.h>
#include <stdlib.h>

#define APP_MENU_COMMAND "/usr/bin/adwaita-lite-app-menu"

typedef struct _PanelWindow PanelWindow;

struct _PanelWindow {
  GtkWidget *window;
  GtkWidget *clock_label;
  GtkWidget *taskbar;
  GtkWidget *network_box;
  GtkWidget *network_image;
  GtkWidget *volume_button;
  GtkWidget *volume_image;
  GtkWidget *backlight_box;
  GtkWidget *backlight_image;
  GtkWidget *battery_box;
  GtkWidget *battery_image;
  guint clock_source;
  PanelShelf *shelf;
};

struct _PanelShelf {
  GtkApplication *app;
  PanelConfig *config;
  GPtrArray *windows;
  ToplevelService *toplevels;
  PanelStatus *status;
  PanelAudio *audio;
  GtkWidget *popover;
  gboolean rebuilding;
};

static gboolean clock_tick(gpointer data);

static int shelf_thickness(PanelShelf *shelf) {
  gboolean compact = panel_config_compact(shelf->config);
  gboolean vertical = panel_config_vertical(shelf->config);
  return vertical ? (compact ? 48 : 64) : (compact ? 40 : 48);
}

static int shelf_icon(PanelShelf *shelf, const char *kind) {
  gboolean compact = panel_config_compact(shelf->config);
  if (g_strcmp0(kind, "app") == 0) return compact ? 24 : 32;
  if (g_strcmp0(kind, "launcher") == 0) return compact ? 20 : 24;
  return compact ? 16 : 20;
}

static void anchor_edges(const char *edge, GtkLayerShellEdge *a, GtkLayerShellEdge *b,
    GtkLayerShellEdge *panel_edge) {
  if (g_strcmp0(edge, "top") == 0) {
    *a = GTK_LAYER_SHELL_EDGE_LEFT;
    *b = GTK_LAYER_SHELL_EDGE_RIGHT;
    *panel_edge = GTK_LAYER_SHELL_EDGE_TOP;
  } else if (g_strcmp0(edge, "left") == 0) {
    *a = GTK_LAYER_SHELL_EDGE_TOP;
    *b = GTK_LAYER_SHELL_EDGE_BOTTOM;
    *panel_edge = GTK_LAYER_SHELL_EDGE_LEFT;
  } else if (g_strcmp0(edge, "right") == 0) {
    *a = GTK_LAYER_SHELL_EDGE_TOP;
    *b = GTK_LAYER_SHELL_EDGE_BOTTOM;
    *panel_edge = GTK_LAYER_SHELL_EDGE_RIGHT;
  } else {
    *a = GTK_LAYER_SHELL_EDGE_LEFT;
    *b = GTK_LAYER_SHELL_EDGE_RIGHT;
    *panel_edge = GTK_LAYER_SHELL_EDGE_BOTTOM;
  }
}

static void clear_focus(GtkWindow *window) {
  gtk_window_set_focus(window, NULL);
}

static void launch_app_menu(GtkButton *button, gpointer data) {
  (void)button; (void)data;
  GError *error = NULL;
  if (!g_spawn_command_line_async(APP_MENU_COMMAND, &error)) {
    g_warning("panel: could not launch app menu: %s",
        error ? error->message : "unknown");
    g_clear_error(&error);
  }
}

static void popover_closed(GtkWidget *pop, gpointer data) {
  PanelShelf *shelf = data;
  if (shelf->popover == pop) shelf->popover = NULL;
  gtk_widget_unparent(pop);
}

static GtkWidget *make_popover(PanelShelf *shelf, GtkWidget *anchor) {
  if (shelf->popover) {
    GtkWidget *old = shelf->popover;
    shelf->popover = NULL;
    gtk_widget_unparent(old);
  }
  GtkWidget *pop = gtk_popover_new();
  gtk_popover_set_autohide(GTK_POPOVER(pop), TRUE);
  gtk_popover_set_has_arrow(GTK_POPOVER(pop), FALSE);
  gtk_popover_set_position(GTK_POPOVER(pop), GTK_POS_TOP);
  gtk_widget_set_parent(pop, anchor);
  shelf->popover = pop;
  g_signal_connect(pop, "closed", G_CALLBACK(popover_closed), shelf);
  return pop;
}

static void show_clock_popup(GtkButton *button, gpointer data) {
  PanelShelf *shelf = data;
  if (panel_config_vertical(shelf->config)) return;

  GtkWidget *pop = make_popover(shelf, GTK_WIDGET(button));
  GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 6);
  gtk_widget_set_margin_top(box, 12);
  gtk_widget_set_margin_bottom(box, 12);
  gtk_widget_set_margin_start(box, 16);
  gtk_widget_set_margin_end(box, 16);

  GtkWidget *title = gtk_label_new("Clock");
  gtk_widget_add_css_class(title, "popover-title");
  gtk_box_append(GTK_BOX(box), title);

  GDateTime *now = g_date_time_new_now_local();
  char *text = g_date_time_format(now, "%A, %B %e, %Y\n%H:%M:%S");
  gtk_box_append(GTK_BOX(box), gtk_label_new(text));
  g_free(text);
  g_date_time_unref(now);

  GtkWidget *close = gtk_button_new_with_label("Close");
  gtk_widget_add_css_class(close, "popover-row");
  g_signal_connect_swapped(close, "clicked", G_CALLBACK(gtk_popover_popdown), pop);
  gtk_box_append(GTK_BOX(box), close);

  gtk_popover_set_child(GTK_POPOVER(pop), box);
  gtk_popover_popup(GTK_POPOVER(pop));
  gtk_widget_grab_focus(close);
}

static GtkWidget *icon_button(const char *icon, const char *name,
    const char *css_class, int size) {
  GtkWidget *button = gtk_button_new();
  GtkWidget *image = gtk_image_new_from_icon_name(icon);
  gtk_image_set_pixel_size(GTK_IMAGE(image), size);
  gtk_button_set_child(GTK_BUTTON(button), image);
  gtk_widget_add_css_class(button, css_class);
  gtk_accessible_update_property(GTK_ACCESSIBLE(button),
      GTK_ACCESSIBLE_PROPERTY_LABEL, name, -1);
  gtk_widget_set_tooltip_text(button, name);
  return button;
}

static void format_clock(PanelShelf *shelf, PanelWindow *window) {
  GDateTime *now = g_date_time_new_now_local();
  const char *pattern = shelf->config->clock_24h ? "%H:%M" : "%I:%M %p";
  char *text = g_date_time_format(now, pattern);
  gtk_label_set_text(GTK_LABEL(window->clock_label), text);
  char *full = g_date_time_format(now, "%A, %B %e, %Y %H:%M:%S");
  gtk_widget_set_tooltip_text(window->clock_label, full);
  gtk_accessible_update_property(GTK_ACCESSIBLE(window->clock_label),
      GTK_ACCESSIBLE_PROPERTY_LABEL, text, -1);
  g_free(text);
  g_free(full);
  g_date_time_unref(now);
}

static void schedule_clock(PanelWindow *window) {
  if (window->clock_source) g_source_remove(window->clock_source);
  GDateTime *now = g_date_time_new_now_local();
  int seconds = g_date_time_get_second(now);
  g_date_time_unref(now);
  int delay = 60 - seconds;
  if (delay <= 0) delay = 1;
  window->clock_source = g_timeout_add_seconds(delay, clock_tick, window);
}

static gboolean clock_tick(gpointer data) {
  PanelWindow *window = data;
  window->clock_source = 0;
  format_clock(window->shelf, window);
  schedule_clock(window);
  return G_SOURCE_REMOVE;
}

static void on_group_clicked(GtkButton *button, gpointer data) {
  toplevel_group_activate(data, GTK_WIDGET(button));
}

static void on_group_middle(GtkGestureClick *gesture, int n_press, double x, double y, gpointer data) {
  (void)n_press; (void)x; (void)y;
  GtkWidget *anchor = gtk_event_controller_get_widget(GTK_EVENT_CONTROLLER(gesture));
  toplevel_group_middle(data, anchor);
}

static void on_group_secondary(GtkGestureClick *gesture, int n_press, double x, double y, gpointer data) {
  (void)n_press; (void)x; (void)y;
  GtkWidget *anchor = gtk_event_controller_get_widget(GTK_EVENT_CONTROLLER(gesture));
  toplevel_group_show_windows(data, anchor);
}

static GtkWidget *group_button(PanelShelf *shelf, AppGroup *group) {
  GtkWidget *button = gtk_button_new();
  GtkWidget *image = gtk_image_new_from_icon_name(
      group->icon && group->icon[0] ? group->icon : "application-x-executable");
  gtk_image_set_pixel_size(GTK_IMAGE(image), shelf_icon(shelf, "app"));
  gtk_button_set_child(GTK_BUTTON(button), image);
  gtk_widget_add_css_class(button, "tile");
  if (group->focused) gtk_widget_add_css_class(button, "focused");
  if (group->windows->len > 0 && !group->focused)
    gtk_widget_add_css_class(button, "running");
  if (group->windows->len == 0 && group->pinned)
    gtk_widget_add_css_class(button, "pinned-idle");

  char *tooltip;
  if (group->windows->len > 1)
    tooltip = g_strdup_printf("%s — %u windows", group->name, group->windows->len);
  else if (group->windows->len == 1)
    tooltip = g_strdup_printf("%s — %s", group->name,
        ((PanelToplevel *)g_ptr_array_index(group->windows, 0))->title);
  else
    tooltip = g_strdup_printf("%s — not running", group->name);
  gtk_widget_set_tooltip_text(button, tooltip);
  gtk_accessible_update_property(GTK_ACCESSIBLE(button),
      GTK_ACCESSIBLE_PROPERTY_LABEL, tooltip, -1);
  g_free(tooltip);

  g_object_set_data(G_OBJECT(button), "group", group);
  g_signal_connect(button, "clicked", G_CALLBACK(on_group_clicked), group);

  GtkGesture *middle = gtk_gesture_click_new();
  gtk_gesture_single_set_button(GTK_GESTURE_SINGLE(middle), GDK_BUTTON_MIDDLE);
  g_signal_connect(middle, "pressed", G_CALLBACK(on_group_middle), group);
  gtk_widget_add_controller(button, GTK_EVENT_CONTROLLER(middle));

  GtkGesture *secondary = gtk_gesture_click_new();
  gtk_gesture_single_set_button(GTK_GESTURE_SINGLE(secondary), GDK_BUTTON_SECONDARY);
  g_signal_connect(secondary, "pressed", G_CALLBACK(on_group_secondary), group);
  gtk_widget_add_controller(button, GTK_EVENT_CONTROLLER(secondary));

  if (panel_config_vertical(shelf->config)) gtk_widget_set_halign(button, GTK_ALIGN_CENTER);
  return button;
}

static void rebuild_taskbars(PanelShelf *shelf) {
  if (!shelf->toplevels) return;
  GPtrArray *groups = toplevel_service_groups(shelf->toplevels);
  for (guint i = 0; i < shelf->windows->len; i++) {
    PanelWindow *window = g_ptr_array_index(shelf->windows, i);
    GtkWidget *child;
    while ((child = gtk_widget_get_first_child(window->taskbar)))
      gtk_box_remove(GTK_BOX(window->taskbar), child);
    for (guint j = 0; j < groups->len; j++)
      gtk_box_append(GTK_BOX(window->taskbar),
          group_button(shelf, g_ptr_array_index(groups, j)));
  }
}

static void on_toplevels_changed(gpointer data) {
  PanelShelf *shelf = data;
  if (!shelf->rebuilding) rebuild_taskbars(shelf);
}

static void on_window_row_clicked(GtkButton *button, gpointer data) {
  PanelToplevel *window = data;
  GtkWidget *pop = gtk_widget_get_ancestor(GTK_WIDGET(button), GTK_TYPE_POPOVER);
  toplevel_window_activate(window);
  if (pop) gtk_popover_popdown(GTK_POPOVER(pop));
}

static void show_window_list(gpointer data, AppGroup *group, GtkWidget *anchor) {
  PanelShelf *shelf = data;
  if (panel_config_vertical(shelf->config)) return;

  GtkWidget *pop = make_popover(shelf, anchor);
  GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 4);
  gtk_widget_set_margin_top(box, 12);
  gtk_widget_set_margin_bottom(box, 12);
  gtk_widget_set_margin_start(box, 16);
  gtk_widget_set_margin_end(box, 16);
  GtkWidget *title = gtk_label_new(group->name);
  gtk_widget_add_css_class(title, "popover-title");
  gtk_box_append(GTK_BOX(box), title);

  GtkWidget *first_row = NULL;
  for (guint i = 0; i < group->windows->len; i++) {
    PanelToplevel *window = g_ptr_array_index(group->windows, i);
    GtkWidget *row = gtk_button_new_with_label(window->title && window->title[0] ?
        window->title : "Untitled window");
    gtk_widget_add_css_class(row, "popover-row");
    g_signal_connect(row, "clicked", G_CALLBACK(on_window_row_clicked), window);
    gtk_box_append(GTK_BOX(box), row);
    if (!first_row) first_row = row;
  }

  GtkWidget *close = gtk_button_new_with_label("Close");
  gtk_widget_add_css_class(close, "popover-row");
  g_signal_connect_swapped(close, "clicked", G_CALLBACK(gtk_popover_popdown), pop);
  gtk_box_append(GTK_BOX(box), close);

  gtk_popover_set_child(GTK_POPOVER(pop), box);
  gtk_popover_popup(GTK_POPOVER(pop));
  gtk_widget_grab_focus(first_row ? first_row : close);
}

static GtkWidget *status_icon_box(const char *icon, const char *name, int size) {
  GtkWidget *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
  gtk_widget_add_css_class(box, "status");
  GtkWidget *image = gtk_image_new_from_icon_name(icon);
  gtk_image_set_pixel_size(GTK_IMAGE(image), size);
  gtk_box_append(GTK_BOX(box), image);
  gtk_widget_set_tooltip_text(box, name);
  gtk_accessible_update_property(GTK_ACCESSIBLE(box),
      GTK_ACCESSIBLE_PROPERTY_LABEL, name, -1);
  gtk_accessible_update_property(GTK_ACCESSIBLE(box),
      GTK_ACCESSIBLE_PROPERTY_DESCRIPTION, name, -1);
  return box;
}

static void show_volume_popup(GtkButton *button, gpointer data) {
  (void)button; (void)data;
  char *path = g_find_program_in_path("pavucontrol");
  if (!path) return;
  GError *error = NULL;
  if (!g_spawn_command_line_async(path, &error)) {
    g_warning("panel: pavucontrol: %s", error ? error->message : "unknown");
    g_clear_error(&error);
  }
  g_free(path);
}

static gboolean volume_scroll(GtkEventControllerScroll *controller, double dx,
    double dy, gpointer data) {
  (void)controller; (void)dx;
  PanelShelf *shelf = data;
  if (dy == 0) return GDK_EVENT_PROPAGATE;
  int steps = (int)(dy < 0 ? -dy : dy);
  if (steps < 1) steps = 1;
  if (steps > 4) steps = 4;
  panel_audio_step(shelf->audio, (dy < 0 ? 1 : -1) * steps * 5);
  return GDK_EVENT_STOP;
}

static gboolean volume_key(GtkEventControllerKey *controller, guint keyval,
    guint keycode, GdkModifierType state, gpointer data) {
  (void)controller; (void)keycode; (void)state;
  PanelShelf *shelf = data;
  if (keyval == GDK_KEY_Up || keyval == GDK_KEY_KP_Up) {
    panel_audio_step(shelf->audio, 5);
    return GDK_EVENT_STOP;
  }
  if (keyval == GDK_KEY_Down || keyval == GDK_KEY_KP_Down) {
    panel_audio_step(shelf->audio, -5);
    return GDK_EVENT_STOP;
  }
  return GDK_EVENT_PROPAGATE;
}

static void panel_shelf_refresh_status(PanelShelf *shelf);

static void on_audio_changed(gpointer data) {
  PanelShelf *shelf = data;
  if (!shelf->rebuilding) panel_shelf_refresh_status(shelf);
}

static void on_status_changed(gpointer data) {
  PanelShelf *shelf = data;
  if (!shelf->rebuilding) panel_shelf_refresh_status(shelf);
}

static void volume_update(PanelWindow *window) {
  PanelShelf *shelf = window->shelf;
  if (!shelf->audio) return;
  PanelAudioState state;
  panel_audio_get_state(shelf->audio, &state);
  const char *icon = "audio-volume-muted-symbolic";
  char *tooltip = NULL;
  char *label = NULL;

  switch (state.status) {
    case AUDIO_READY:
      if (state.muted) {
        icon = "audio-volume-muted-symbolic";
        tooltip = g_strdup_printf("Muted, %d%%", state.percent);
        label = g_strdup_printf("Volume, muted, %d percent", state.percent);
      } else if (state.percent >= 66) {
        icon = "audio-volume-high-symbolic";
        tooltip = g_strdup_printf("%d%%", state.percent);
        label = g_strdup_printf("Volume, %d percent", state.percent);
      } else if (state.percent >= 33) {
        icon = "audio-volume-medium-symbolic";
        tooltip = g_strdup_printf("%d%%", state.percent);
        label = g_strdup_printf("Volume, %d percent", state.percent);
      } else {
        icon = "audio-volume-low-symbolic";
        tooltip = g_strdup_printf("%d%%", state.percent);
        label = g_strdup_printf("Volume, %d percent", state.percent);
      }
      break;
    case AUDIO_CONNECTING:
      icon = "audio-volume-medium-symbolic";
      tooltip = g_strdup("Volume");
      label = g_strdup("Volume");
      break;
    case AUDIO_NO_SINK:
      tooltip = g_strdup("No audio output");
      label = g_strdup("Volume, no audio output");
      break;
    case AUDIO_UNAVAILABLE:
      tooltip = g_strdup("Audio unavailable");
      label = g_strdup("Volume, audio unavailable");
      break;
  }

  gtk_image_set_from_icon_name(GTK_IMAGE(window->volume_image), icon);
  gtk_widget_set_tooltip_text(window->volume_button, tooltip);
  gtk_accessible_update_property(GTK_ACCESSIBLE(window->volume_button),
      GTK_ACCESSIBLE_PROPERTY_LABEL, label, -1);
  g_free(tooltip);
  g_free(label);
}

static void panel_shelf_refresh_status(PanelShelf *shelf) {
  if (!shelf || !shelf->windows || !shelf->status) return;
  PanelBatteryView battery;
  PanelNetworkView network;
  PanelBacklightView backlight;
  panel_status_get(shelf->status, &battery, &network, &backlight);

  for (guint i = 0; i < shelf->windows->len; i++) {
    PanelWindow *window = g_ptr_array_index(shelf->windows, i);
    if (window->network_box) {
      gtk_image_set_from_icon_name(GTK_IMAGE(window->network_image),
          network.visible ? network.icon : "network-offline-symbolic");
      gtk_widget_set_tooltip_text(window->network_box,
          network.visible ? network.tooltip : "Network");
      gtk_accessible_update_property(GTK_ACCESSIBLE(window->network_box),
          GTK_ACCESSIBLE_PROPERTY_LABEL,
          network.visible ? network.label : "Network", -1);
      gtk_widget_set_visible(window->network_box, network.visible);
    }
    if (window->backlight_box) {
      gtk_widget_set_tooltip_text(window->backlight_box,
          backlight.visible ? backlight.tooltip : "Brightness");
      gtk_widget_set_visible(window->backlight_box, backlight.visible);
    }
    if (window->battery_box) {
      gtk_image_set_from_icon_name(GTK_IMAGE(window->battery_image),
          battery.visible ? battery.icon : "battery-missing-symbolic");
      gtk_widget_set_tooltip_text(window->battery_box,
          battery.visible ? battery.tooltip : "Battery");
      gtk_accessible_update_property(GTK_ACCESSIBLE(window->battery_box),
          GTK_ACCESSIBLE_PROPERTY_LABEL,
          battery.visible ? battery.label : "Battery", -1);
      gtk_widget_remove_css_class(window->battery_image, "warning");
      gtk_widget_remove_css_class(window->battery_image, "critical");
      if (battery.severity == 1) gtk_widget_add_css_class(window->battery_image, "warning");
      if (battery.severity == 2) gtk_widget_add_css_class(window->battery_image, "critical");
      gtk_widget_set_visible(window->battery_box, battery.visible);
    }
    if (window->volume_button) volume_update(window);
  }
}

static gboolean enable_on_demand(gpointer data) {
  gtk_layer_set_keyboard_mode(GTK_WINDOW(data),
      GTK_LAYER_SHELL_KEYBOARD_MODE_ON_DEMAND);
  return G_SOURCE_REMOVE;
}

static PanelWindow *panel_window_new(PanelShelf *shelf, GdkMonitor *monitor) {
  PanelWindow *window = g_new0(PanelWindow, 1);
  window->shelf = shelf;
  const char *edge = panel_config_edge(shelf->config);
  gboolean vertical = panel_config_vertical(shelf->config);
  int thickness = shelf_thickness(shelf);

  GtkWidget *win = gtk_application_window_new(shelf->app);
  window->window = win;
  gtk_widget_set_name(win, "panel");
  gtk_window_set_decorated(GTK_WINDOW(win), FALSE);
  gtk_layer_init_for_window(GTK_WINDOW(win));
  if (monitor) gtk_layer_set_monitor(GTK_WINDOW(win), monitor);
  gtk_layer_set_layer(GTK_WINDOW(win), GTK_LAYER_SHELL_LAYER_TOP);
  gtk_layer_set_namespace(GTK_WINDOW(win), "adwaita-lite-panel");

  GtkLayerShellEdge first, second, panel_edge;
  anchor_edges(edge, &first, &second, &panel_edge);
  gtk_layer_set_anchor(GTK_WINDOW(win), first, TRUE);
  gtk_layer_set_anchor(GTK_WINDOW(win), second, TRUE);
  gtk_layer_set_anchor(GTK_WINDOW(win), panel_edge, TRUE);
  gtk_layer_set_exclusive_zone(GTK_WINDOW(win), thickness);
  gtk_layer_set_keyboard_mode(GTK_WINDOW(win),
      GTK_LAYER_SHELL_KEYBOARD_MODE_NONE);

  GtkWidget *shelf_box = gtk_box_new(
      vertical ? GTK_ORIENTATION_VERTICAL : GTK_ORIENTATION_HORIZONTAL, 4);
  gtk_widget_add_css_class(shelf_box, "shelf");
  if (vertical) gtk_widget_set_size_request(shelf_box, thickness, -1);
  else gtk_widget_set_size_request(shelf_box, -1, thickness);

  GtkWidget *start = gtk_box_new(
      vertical ? GTK_ORIENTATION_VERTICAL : GTK_ORIENTATION_HORIZONTAL, 4);
  GtkWidget *launcher = icon_button("view-app-grid-symbolic", "Applications",
      "launcher", shelf_icon(shelf, "launcher"));
  g_signal_connect(launcher, "clicked", G_CALLBACK(launch_app_menu), NULL);
  if (vertical) gtk_widget_set_margin_bottom(launcher, 6);
  else gtk_widget_set_margin_end(launcher, 6);
  gtk_box_append(GTK_BOX(start), launcher);

  GtkWidget *taskbar = gtk_box_new(
      vertical ? GTK_ORIENTATION_VERTICAL : GTK_ORIENTATION_HORIZONTAL, 4);
  gtk_box_append(GTK_BOX(start), taskbar);
  window->taskbar = taskbar;

  GtkWidget *spacer = gtk_box_new(
      vertical ? GTK_ORIENTATION_VERTICAL : GTK_ORIENTATION_HORIZONTAL, 0);
  if (vertical) gtk_widget_set_vexpand(spacer, TRUE);
  else gtk_widget_set_hexpand(spacer, TRUE);

  GtkWidget *end = gtk_box_new(
      vertical ? GTK_ORIENTATION_VERTICAL : GTK_ORIENTATION_HORIZONTAL, 4);

  window->network_box = status_icon_box("network-wired-symbolic", "Network",
      shelf_icon(shelf, "status"));
  window->network_image = gtk_widget_get_first_child(window->network_box);
  gtk_box_append(GTK_BOX(end), window->network_box);

  GtkWidget *volume = gtk_button_new();
  gtk_widget_add_css_class(volume, "status");
  GtkWidget *volume_image = gtk_image_new_from_icon_name("audio-volume-medium-symbolic");
  gtk_image_set_pixel_size(GTK_IMAGE(volume_image), shelf_icon(shelf, "status"));
  gtk_button_set_child(GTK_BUTTON(volume), volume_image);
  gtk_widget_set_tooltip_text(volume, "Volume");
  gtk_accessible_update_property(GTK_ACCESSIBLE(volume),
      GTK_ACCESSIBLE_PROPERTY_LABEL, "Volume", -1);
  g_signal_connect(volume, "clicked", G_CALLBACK(show_volume_popup), shelf);
  GtkEventController *scroll = gtk_event_controller_scroll_new(
      GTK_EVENT_CONTROLLER_SCROLL_VERTICAL | GTK_EVENT_CONTROLLER_SCROLL_DISCRETE);
  g_signal_connect(scroll, "scroll", G_CALLBACK(volume_scroll), shelf);
  gtk_widget_add_controller(volume, scroll);
  GtkEventController *vkey = gtk_event_controller_key_new();
  g_signal_connect(vkey, "key-pressed", G_CALLBACK(volume_key), shelf);
  gtk_widget_add_controller(volume, vkey);
  window->volume_button = volume;
  window->volume_image = volume_image;
  gtk_box_append(GTK_BOX(end), volume);

  window->backlight_box = status_icon_box("display-brightness-symbolic", "Brightness",
      shelf_icon(shelf, "status"));
  window->backlight_image = gtk_widget_get_first_child(window->backlight_box);
  gtk_box_append(GTK_BOX(end), window->backlight_box);

  window->battery_box = status_icon_box("battery-level-80-symbolic", "Battery",
      shelf_icon(shelf, "status"));
  window->battery_image = gtk_widget_get_first_child(window->battery_box);
  gtk_box_append(GTK_BOX(end), window->battery_box);

  GtkWidget *clock_button = gtk_button_new();
  gtk_widget_add_css_class(clock_button, "clock-button");
  gtk_widget_set_tooltip_text(clock_button, "Clock");
  GtkWidget *clock = gtk_label_new("");
  gtk_widget_add_css_class(clock, "clock");
  gtk_button_set_child(GTK_BUTTON(clock_button), clock);
  g_signal_connect(clock_button, "clicked", G_CALLBACK(show_clock_popup), shelf);
  gtk_accessible_update_property(GTK_ACCESSIBLE(clock_button),
      GTK_ACCESSIBLE_PROPERTY_DESCRIPTION, "Shows the current time", -1);
  gtk_box_append(GTK_BOX(end), clock_button);
  window->clock_label = clock;

  if (vertical) {
    for (GtkWidget *child = gtk_widget_get_first_child(GTK_WIDGET(start)); child;
         child = gtk_widget_get_next_sibling(child))
      gtk_widget_set_halign(child, GTK_ALIGN_CENTER);
    for (GtkWidget *child = gtk_widget_get_first_child(GTK_WIDGET(end)); child;
         child = gtk_widget_get_next_sibling(child))
      gtk_widget_set_halign(child, GTK_ALIGN_CENTER);
  }

  gtk_box_append(GTK_BOX(shelf_box), start);
  gtk_box_append(GTK_BOX(shelf_box), spacer);
  gtk_box_append(GTK_BOX(shelf_box), end);
  gtk_window_set_child(GTK_WINDOW(win), shelf_box);
  gtk_window_present(GTK_WINDOW(win));
  clear_focus(GTK_WINDOW(win));
  g_timeout_add(500, enable_on_demand, win);

  format_clock(shelf, window);
  schedule_clock(window);
  if (shelf->status) panel_shelf_refresh_status(shelf);
  return window;
}

static void panel_window_free(PanelWindow *window) {
  if (window->clock_source) g_source_remove(window->clock_source);
  gtk_window_destroy(GTK_WINDOW(window->window));
  g_free(window);
}

PanelShelf *panel_shelf_new(GtkApplication *app, PanelConfig *config) {
  PanelShelf *shelf = g_new0(PanelShelf, 1);
  shelf->app = app;
  shelf->config = config;
  shelf->windows = g_ptr_array_new_with_free_func((GDestroyNotify)panel_window_free);
  shelf->status = panel_status_new(config, on_status_changed, shelf);
  shelf->audio = panel_audio_new(on_audio_changed, shelf);
  shelf->toplevels = toplevel_service_new(config, show_window_list,
      on_toplevels_changed, shelf);
  panel_shelf_reload(shelf, config);
  panel_audio_start(shelf->audio);
  panel_shelf_refresh_status(shelf);
  return shelf;
}

void panel_shelf_reload(PanelShelf *shelf, PanelConfig *config) {
  shelf->config = config;
  shelf->rebuilding = TRUE;
  g_ptr_array_set_size(shelf->windows, 0);

  GdkDisplay *display = gdk_display_get_default();
  GListModel *monitors = gdk_display_get_monitors(display);
  guint count = g_list_model_get_n_items(monitors);
  for (guint i = 0; i < count; i++) {
    GdkMonitor *monitor = g_list_model_get_item(monitors, i);
    PanelWindow *window = panel_window_new(shelf, monitor);
    g_ptr_array_add(shelf->windows, window);
    g_object_unref(monitor);
  }
  if (count == 0) g_ptr_array_add(shelf->windows, panel_window_new(shelf, NULL));
  shelf->rebuilding = FALSE;
  if (shelf->status) panel_status_set_config(shelf->status, config);
  if (shelf->toplevels) toplevel_service_reload_pins(shelf->toplevels, config);
  else rebuild_taskbars(shelf);
  panel_shelf_refresh_status(shelf);
}

void panel_shelf_free(PanelShelf *shelf) {
  if (!shelf) return;
  if (shelf->popover) {
    gtk_widget_unparent(shelf->popover);
    shelf->popover = NULL;
  }
  panel_audio_free(shelf->audio);
  panel_status_free(shelf->status);
  g_ptr_array_unref(shelf->windows);
  toplevel_service_free(shelf->toplevels);
  g_free(shelf);
}
