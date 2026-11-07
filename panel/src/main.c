/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <gtk/gtk.h>

#include "config.h"
#include "shelf.h"
#include "theme.h"

static PanelConfig *config;
static PanelShelf *shelf;
static GtkCssProvider *provider;
static guint reload_source;

static void apply_theme(void) {
  char *css = panel_theme_css(config);
  gtk_css_provider_load_from_string(provider, css);
  g_free(css);
}

static gboolean reload_now(gpointer data) {
  (void)data;
  reload_source = 0;
  PanelConfig *fresh = panel_config_load();
  panel_config_free(config);
  config = fresh;
  apply_theme();
  panel_shelf_reload(shelf, config);
  return G_SOURCE_REMOVE;
}

static void on_settings_changed(GFileMonitor *monitor, GFile *file, GFile *other,
    GFileMonitorEvent event, gpointer data) {
  (void)monitor; (void)file; (void)other; (void)data;
  if (event == G_FILE_MONITOR_EVENT_CHANGES_DONE_HINT ||
      event == G_FILE_MONITOR_EVENT_CREATED ||
      event == G_FILE_MONITOR_EVENT_ATTRIBUTE_CHANGED) {
    if (reload_source) g_source_remove(reload_source);
    reload_source = g_timeout_add(150, reload_now, NULL);
  }
}

static void watch_settings(void) {
  char *dir_path = g_build_filename(g_get_home_dir(), ".config", "adwaita-lite", NULL);
  GFile *dir = g_file_new_for_path(dir_path);
  GError *error = NULL;
  GFileMonitor *monitor = g_file_monitor_directory(dir, G_FILE_MONITOR_NONE, NULL, &error);
  if (monitor) {
    g_signal_connect(monitor, "changed", G_CALLBACK(on_settings_changed), NULL);
  } else {
    g_warning("panel: could not watch %s: %s", dir_path,
        error ? error->message : "unknown");
    g_clear_error(&error);
  }
  g_object_unref(dir);
  g_free(dir_path);
}

static void activate(GtkApplication *app, gpointer data) {
  (void)data;
  config = panel_config_load();
  provider = gtk_css_provider_new();
  gtk_style_context_add_provider_for_display(gdk_display_get_default(),
      GTK_STYLE_PROVIDER(provider), GTK_STYLE_PROVIDER_PRIORITY_USER);
  apply_theme();
  shelf = panel_shelf_new(app, config);
  watch_settings();
}

static void shutdown(GApplication *app, gpointer data) {
  (void)app; (void)data;
  if (reload_source) g_source_remove(reload_source);
  panel_shelf_free(shelf);
  shelf = NULL;
  panel_config_free(config);
  config = NULL;
  g_clear_object(&provider);
}

int main(int argc, char **argv) {
  g_setenv("GSK_RENDERER", "cairo", TRUE);
  GtkApplication *app = gtk_application_new("org.adwaita.lite.Panel",
      G_APPLICATION_DEFAULT_FLAGS);
  g_signal_connect(app, "activate", G_CALLBACK(activate), NULL);
  g_signal_connect(app, "shutdown", G_CALLBACK(shutdown), NULL);
  int status = g_application_run(G_APPLICATION(app), argc, argv);
  g_object_unref(app);
  return status;
}
