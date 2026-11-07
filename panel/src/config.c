/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "config.h"

#include <json-glib/json-glib.h>
#include <stdio.h>
#include <string.h>

#define DEFAULT_SETTINGS "/usr/share/adwaita-lite/defaults/settings.json"

static const char *valid_edges[] = {"bottom", "top", "left", "right", NULL};
static const char *valid_density[] = {"normal", "compact", NULL};
static const char *valid_theme[] = {"light", "dark", NULL};

static gboolean string_in_list(const char *value, const char *const *list) {
  for (int i = 0; list[i]; i++)
    if (g_strcmp0(value, list[i]) == 0) return TRUE;
  return FALSE;
}

static char *read_string(JsonObject *object, const char *key, const char *fallback) {
  if (json_object_has_member(object, key)) {
    JsonNode *node = json_object_get_member(object, key);
    if (json_node_get_value_type(node) == G_TYPE_STRING)
      return g_strdup(json_node_get_string(node));
  }
  return g_strdup(fallback);
}

static gboolean read_bool(JsonObject *object, const char *key, gboolean fallback) {
  if (json_object_has_member(object, key)) {
    JsonNode *node = json_object_get_member(object, key);
    if (json_node_get_value_type(node) == G_TYPE_BOOLEAN)
      return json_node_get_boolean(node);
  }
  return fallback;
}

static int read_int(JsonObject *object, const char *key, int fallback) {
  if (json_object_has_member(object, key)) {
    JsonNode *node = json_object_get_member(object, key);
    if (json_node_get_value_type(node) == G_TYPE_INT64)
      return (int)json_node_get_int(node);
  }
  return fallback;
}

static JsonObject *load_object(JsonParser *parser, const char *path) {
  GError *error = NULL;
  if (!json_parser_load_from_file(parser, path, &error)) {
    g_clear_error(&error);
    return NULL;
  }
  JsonNode *root = json_parser_get_root(parser);
  if (!root || json_node_get_node_type(root) != JSON_NODE_OBJECT) return NULL;
  return json_node_get_object(root);
}

PanelConfig *panel_config_load_defaults(void) {
  PanelConfig *config = g_new0(PanelConfig, 1);
  config->edge = g_strdup("bottom");
  config->density = g_strdup("normal");
  config->theme = g_strdup("light");
  config->accent = g_strdup("blue");
  config->font_size = 11;
  config->high_contrast = FALSE;
  config->reduce_motion = FALSE;
  config->clock_24h = FALSE;
  config->panel_twilight = FALSE;
  return config;
}

PanelConfig *panel_config_load(void) {
  PanelConfig *config = panel_config_load_defaults();
  JsonParser *parser = json_parser_new();
  JsonObject *object = load_object(parser, DEFAULT_SETTINGS);
  if (object) {
    g_free(config->edge);
    config->edge = read_string(object, "edge", "bottom");
    g_free(config->density);
    config->density = read_string(object, "density", "normal");
    g_free(config->theme);
    config->theme = read_string(object, "theme", "light");
    g_free(config->accent);
    config->accent = read_string(object, "accent", "blue");
    config->font_size = read_int(object, "font_size", 11);
    config->high_contrast = read_bool(object, "high_contrast", FALSE);
    config->reduce_motion = read_bool(object, "reduce_motion", FALSE);
    config->clock_24h = read_bool(object, "clock_24h", FALSE);
    config->panel_twilight = read_bool(object, "panel_twilight", FALSE);
  }
  g_object_unref(parser);

  const char *home = g_get_home_dir();
  char *user_path = g_build_filename(home, ".config", "adwaita-lite", "settings.json", NULL);
  parser = json_parser_new();
  object = load_object(parser, user_path);
  if (object) {
    g_free(config->edge);
    config->edge = read_string(object, "edge", "bottom");
    g_free(config->density);
    config->density = read_string(object, "density", "normal");
    g_free(config->theme);
    config->theme = read_string(object, "theme", "light");
    g_free(config->accent);
    config->accent = read_string(object, "accent", "blue");
    config->font_size = read_int(object, "font_size", 11);
    config->high_contrast = read_bool(object, "high_contrast", FALSE);
    config->reduce_motion = read_bool(object, "reduce_motion", FALSE);
    config->clock_24h = read_bool(object, "clock_24h", FALSE);
    config->panel_twilight = read_bool(object, "panel_twilight", FALSE);
  }
  g_object_unref(parser);
  g_free(user_path);

  if (!string_in_list(config->edge, valid_edges)) {
    g_free(config->edge);
    config->edge = g_strdup("bottom");
  }
  if (!string_in_list(config->density, valid_density)) {
    g_free(config->density);
    config->density = g_strdup("normal");
  }
  if (!string_in_list(config->theme, valid_theme)) {
    g_free(config->theme);
    config->theme = g_strdup("light");
  }
  if (config->font_size < 10 || config->font_size > 15) config->font_size = 11;
  return config;
}

void panel_config_free(PanelConfig *config) {
  if (!config) return;
  g_free(config->edge);
  g_free(config->density);
  g_free(config->theme);
  g_free(config->accent);
  g_free(config);
}

const char *panel_config_edge(const PanelConfig *config) {
  return config->edge ? config->edge : "bottom";
}

gboolean panel_config_vertical(const PanelConfig *config) {
  return g_strcmp0(panel_config_edge(config), "left") == 0 ||
         g_strcmp0(panel_config_edge(config), "right") == 0;
}

gboolean panel_config_compact(const PanelConfig *config) {
  return g_strcmp0(config->density, "compact") == 0;
}

gboolean panel_config_dark(const PanelConfig *config) {
  gboolean dark = g_strcmp0(config->theme, "dark") == 0;
  if (config->panel_twilight && !config->high_contrast) dark = !dark;
  return dark;
}
