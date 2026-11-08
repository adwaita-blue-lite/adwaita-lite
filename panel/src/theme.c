/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "theme.h"

#include <glib.h>
#include <stdio.h>
#include <string.h>

typedef struct {
  const char *name;
  const char *hex;
} Accent;

static const Accent accents[] = {
  {"blue", "#3584e4"}, {"teal", "#2190a4"}, {"green", "#3a944a"},
  {"yellow", "#c88800"}, {"orange", "#ed5b00"}, {"red", "#e62d42"},
  {"pink", "#d56199"}, {"purple", "#9141ac"}, {"slate", "#6f8396"},
  {NULL, NULL},
};

static const char *accent_hex(const char *name) {
  for (int i = 0; accents[i].name; i++)
    if (g_strcmp0(name, accents[i].name) == 0) return accents[i].hex;
  return "#3584e4";
}

char *panel_theme_css(const PanelConfig *config) {
  gboolean compact = panel_config_compact(config);
  gboolean vertical = panel_config_vertical(config);
  gboolean hc = config->high_contrast;
  gboolean dark = panel_config_dark(config);
  int size = vertical ? (compact ? 48 : 64) : (compact ? 40 : 48);
  int tile = compact ? 40 : 48;
  int radius = compact ? 10 : 12;
  int icon_app = compact ? 24 : 32;
  int icon_launcher = compact ? 20 : 24;
  int icon_status = compact ? 16 : 20;
  int body = config->font_size + 2;
  int clock_size = body - (compact ? 1 : 0);
  int clock_min = compact ? 52 : 58;
  int clock_pad = compact ? 8 : 10;
  int inset = 16;
  int gap = 4;
  const char *accent = accent_hex(config->accent);
  const char *surface = hc ? "#000000" : (dark ? "#222226" : "#fafafa");
  const char *fg = hc ? "#ffffff" : (dark ? "#ffffff" : "#1e1e1e");
  const char *card = hc ? "#1d1d20" : (dark ? "#36363a" : "#ffffff");
  const char *border = hc ? "rgba(255, 255, 255, 0.55)" :
      (dark ? "rgba(255, 255, 255, 0.14)" : "rgba(30, 30, 30, 0.10)");
  const char *hover = hc ? "rgba(255, 255, 255, 0.20)" :
      (dark ? "rgba(255, 255, 255, 0.10)" : "rgba(30, 30, 30, 0.08)");
  const char *pressed = hc ? "rgba(255, 255, 255, 0.32)" :
      (dark ? "rgba(255, 255, 255, 0.18)" : "rgba(30, 30, 30, 0.16)");
  const char *focused = g_strdup_printf("alpha(%s, 0.14)", accent);
  const char *separator = hc ? "rgba(255, 255, 255, 0.55)" :
      (dark ? "rgba(255, 255, 255, 0.16)" : "rgba(30, 30, 30, 0.12)");
  const char *motion = (config->reduce_motion || hc) ? "none" :
      "background-color 120ms ease-out, box-shadow 120ms ease-out";
  const char *edge = panel_config_edge(config);
  const char *shadow = "inset 0 1px 0 0";
  const char *indicator = "inset 0 -3px 0 0";
  const char *orientation = vertical ? "vertical" : "horizontal";
  if (g_strcmp0(edge, "top") == 0) {
    shadow = "inset 0 -1px 0 0";
    indicator = "inset 0 3px 0 0";
  } else if (g_strcmp0(edge, "left") == 0) {
    shadow = "inset -1px 0 0 0";
    indicator = "inset 3px 0 0 0";
  } else if (g_strcmp0(edge, "right") == 0) {
    shadow = "inset 1px 0 0 0";
    indicator = "inset -3px 0 0 0";
  }

  char *padding = vertical ? g_strdup_printf("%dpx 0", inset)
                          : g_strdup_printf("0 %dpx", inset);
  GString *css = g_string_new(NULL);
  g_string_append_printf(css,
    "window#panel {\n"
    "  background: %s;\n"
    "  color: %s;\n"
    "  border: none;\n"
    "  box-shadow: %s %s;\n"
    "}\n"
    ".shelf {\n"
    "  padding: %s;\n"
    "}\n"
    "button.tile {\n"
    "  min-width: %dpx;\n"
    "  min-height: %dpx;\n"
    "  padding: 0;\n"
    "  border: none;\n"
    "  outline: none;\n"
    "  border-radius: %dpx;\n"
    "  background: transparent;\n"
    "  box-shadow: none;\n"
    "  transition: %s;\n"
    "}\n"
    "button.tile:hover, button.status:hover, button.launcher:hover {\n"
    "  background: %s;\n"
    "}\n"
    "button.tile:active, button.status:active, button.launcher:active {\n"
    "  background: %s;\n"
    "}\n"
    "button.tile:focus, button.status:focus, button.launcher:focus {\n"
    "  box-shadow: inset 0 0 0 2px %s;\n"
    "}\n"
    "button.tile.focused {\n"
    "  background: %s;\n"
    "  box-shadow: %s %s;\n"
    "}\n"
    "button.tile.running {\n"
    "  box-shadow: %s %s;\n"
    "}\n"
    "button.tile.focused:focus {\n"
    "  box-shadow: %s %s, inset 0 0 0 2px %s;\n"
    "}\n"
    "button.launcher {\n"
    "  min-width: %dpx;\n"
    "  min-height: %dpx;\n"
    "  padding: 0;\n"
    "  border: none;\n"
    "  outline: none;\n"
    "  border-radius: 999px;\n"
    "  background: %s;\n"
    "  box-shadow: none;\n"
    "}\n"
    "button.status {\n"
    "  min-width: %dpx;\n"
    "  min-height: %dpx;\n"
    "  padding: 0;\n"
    "  border: none;\n"
    "  outline: none;\n"
    "  border-radius: %dpx;\n"
    "  background: transparent;\n"
    "  box-shadow: none;\n"
    "}\n"
    ".status {\n"
    "  min-width: 40px;\n"
    "  min-height: 40px;\n"
    "  border-radius: 12px;\n"
    "}\n"
    "image.warning { color: #c88800; }\n"
    "image.critical { color: #e62d42; }\n"
    "button.clock-button {\n"
    "  min-width: 40px;\n"
    "  min-height: 40px;\n"
    "  padding: 0;\n"
    "  border: none;\n"
    "  outline: none;\n"
    "  border-radius: 12px;\n"
    "  background: transparent;\n"
    "  box-shadow: none;\n"
    "}\n"
    "button.clock-button:hover { background: %s; }\n"
    "label.clock {\n"
    "  min-width: %dpx;\n"
    "  padding: 0 %dpx;\n"
    "  font-family: \"Adwaita Sans\", \"Inter\", \"Roboto\", sans-serif;\n"
    "  font-size: %dpx;\n"
    "  font-weight: 500;\n"
    "  font-feature-settings: \"tnum\";\n"
    "}\n"
    ".shelf button, .shelf label {\n"
    "  font-family: \"Adwaita Sans\", \"Inter\", \"Roboto\", sans-serif;\n"
    "}\n"
    "popover, popover.background {\n"
    "  background: %s;\n"
    "  color: %s;\n"
    "  border: 1px solid %s;\n"
    "  border-radius: 12px;\n"
    "}\n"
    ".popover-title { font-weight: 600; }\n"
    "button.popover-row {\n"
    "  min-height: 36px;\n"
    "  border-radius: 8px;\n"
    "  background: transparent;\n"
    "}\n"
    "button.popover-row { color: %s; }\n"
    "button.popover-row:hover { background: %s; }\n"
    "tooltip {\n"
    "  background: %s;\n"
    "  color: %s;\n"
    "  border: 1px solid %s;\n"
    "  border-radius: 8px;\n"
    "  padding: 6px 8px;\n"
    "}\n",
    surface, fg, shadow, separator, padding,
    tile, tile, radius, motion, hover, pressed, accent, focused, indicator, accent,
    indicator, accent, indicator, accent, accent,
    tile, tile, hover, 40, 40, radius, hover, clock_min, clock_pad, clock_size,
    card, fg, border, fg, hover, card, fg, border);

  g_free(padding);
  g_free((char *)focused);
  g_string_append_printf(css,
      ".shelf button, .shelf label, .shelf image { color: %s; }\n",
      fg);
  g_string_append_printf(css, "/* orientation: %s; size: %d; gap: %d; icons: %d/%d/%d */\n",
      orientation, size, gap, icon_app, icon_launcher, icon_status);
  return g_string_free(css, FALSE);
}
