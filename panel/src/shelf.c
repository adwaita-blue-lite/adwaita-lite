/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "shelf.h"

#include <gtk4-layer-shell.h>
#include <stdlib.h>

#define APP_MENU_COMMAND "/usr/bin/adwaita-lite-app-menu"

typedef struct _PanelWindow PanelWindow;

struct _PanelWindow {
  GtkWidget *window;
  GtkWidget *clock_label;
  guint clock_source;
  PanelShelf *shelf;
};

struct _PanelShelf {
  GtkApplication *app;
  PanelConfig *config;
  GPtrArray *windows;
  GtkWidget *popup;
  GtkWidget *popup_parent;
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

static void close_popup(PanelShelf *shelf) {
  if (shelf->popup) {
    gtk_window_destroy(GTK_WINDOW(shelf->popup));
    shelf->popup = NULL;
  }
}

static gboolean panel_key(GtkEventControllerKey *controller, guint keyval,
    guint keycode, GdkModifierType state, gpointer data) {
  (void)controller; (void)keycode; (void)state;
  PanelShelf *shelf = data;
  if (keyval == GDK_KEY_Escape && shelf->popup) {
    close_popup(shelf);
    return GDK_EVENT_STOP;
  }
  return GDK_EVENT_PROPAGATE;
}

static gboolean popup_key(GtkEventControllerKey *controller, guint keyval,
    guint keycode, GdkModifierType state, gpointer data) {
  (void)controller; (void)keycode; (void)state;
  PanelShelf *shelf = data;
  if (keyval == GDK_KEY_Escape) {
    close_popup(shelf);
    return GDK_EVENT_STOP;
  }
  return GDK_EVENT_PROPAGATE;
}

static void popup_closed(GtkWidget *window, gpointer data) {
  (void)window;
  PanelShelf *shelf = data;
  if (shelf->popup == GTK_WIDGET(window)) shelf->popup = NULL;
  if (shelf->popup_parent) {
    gtk_layer_set_keyboard_mode(GTK_WINDOW(shelf->popup_parent),
        GTK_LAYER_SHELL_KEYBOARD_MODE_ON_DEMAND);
    shelf->popup_parent = NULL;
  }
}

static void show_clock_popup(GtkButton *button, gpointer data) {
  (void)button;
  PanelShelf *shelf = data;
  close_popup(shelf);
  if (panel_config_vertical(shelf->config)) return;

  GtkNative *native = gtk_widget_get_native(GTK_WIDGET(button));
  if (native) {
    shelf->popup_parent = GTK_WIDGET(native);
    gtk_layer_set_keyboard_mode(GTK_WINDOW(shelf->popup_parent),
        GTK_LAYER_SHELL_KEYBOARD_MODE_EXCLUSIVE);
  }
  GtkWidget *popup = gtk_application_window_new(shelf->app);
  gtk_widget_set_name(popup, "popup");
  gtk_layer_init_for_window(GTK_WINDOW(popup));
  gtk_layer_set_layer(GTK_WINDOW(popup), GTK_LAYER_SHELL_LAYER_OVERLAY);
  gtk_layer_set_anchor(GTK_WINDOW(popup), GTK_LAYER_SHELL_EDGE_RIGHT, TRUE);
  gtk_layer_set_anchor(GTK_WINDOW(popup), GTK_LAYER_SHELL_EDGE_BOTTOM, TRUE);
  gtk_layer_set_margin(GTK_WINDOW(popup), GTK_LAYER_SHELL_EDGE_RIGHT, 16);
  gtk_layer_set_margin(GTK_WINDOW(popup), GTK_LAYER_SHELL_EDGE_BOTTOM,
      shelf_thickness(shelf) + 8);
  gtk_layer_set_keyboard_mode(GTK_WINDOW(popup),
      GTK_LAYER_SHELL_KEYBOARD_MODE_EXCLUSIVE);

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
  g_signal_connect_swapped(close, "clicked", G_CALLBACK(gtk_window_destroy), popup);
  gtk_box_append(GTK_BOX(box), close);

  gtk_window_set_child(GTK_WINDOW(popup), box);
  gtk_window_present(GTK_WINDOW(popup));
  gtk_window_set_focus(GTK_WINDOW(popup), close);

  GtkEventController *key = gtk_event_controller_key_new();
  g_signal_connect(key, "key-pressed", G_CALLBACK(popup_key), shelf);
  gtk_widget_add_controller(popup, key);
  g_signal_connect(popup, "destroy", G_CALLBACK(popup_closed), shelf);
  shelf->popup = popup;
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
      GTK_LAYER_SHELL_KEYBOARD_MODE_ON_DEMAND);

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

  GtkWidget *spacer = gtk_box_new(
      vertical ? GTK_ORIENTATION_VERTICAL : GTK_ORIENTATION_HORIZONTAL, 0);
  if (vertical) gtk_widget_set_vexpand(spacer, TRUE);
  else gtk_widget_set_hexpand(spacer, TRUE);

  GtkWidget *end = gtk_box_new(
      vertical ? GTK_ORIENTATION_VERTICAL : GTK_ORIENTATION_HORIZONTAL, 4);
  gtk_box_append(GTK_BOX(end), icon_button("network-wired-symbolic", "Network, connected",
      "status", shelf_icon(shelf, "status")));
  gtk_box_append(GTK_BOX(end), icon_button("audio-volume-medium-symbolic", "Volume, 42 percent",
      "status", shelf_icon(shelf, "status")));
  gtk_box_append(GTK_BOX(end), icon_button("battery-level-80-symbolic", "Battery, 80 percent",
      "status", shelf_icon(shelf, "status")));

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
  GtkEventController *panel_key_controller = gtk_event_controller_key_new();
  g_signal_connect(panel_key_controller, "key-pressed", G_CALLBACK(panel_key), shelf);
  gtk_widget_add_controller(win, panel_key_controller);

  gtk_window_present(GTK_WINDOW(win));
  clear_focus(GTK_WINDOW(win));

  format_clock(shelf, window);
  schedule_clock(window);
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
  panel_shelf_reload(shelf, config);
  return shelf;
}

void panel_shelf_reload(PanelShelf *shelf, PanelConfig *config) {
  shelf->config = config;
  close_popup(shelf);
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
}

void panel_shelf_free(PanelShelf *shelf) {
  if (!shelf) return;
  close_popup(shelf);
  g_ptr_array_unref(shelf->windows);
  g_free(shelf);
}
