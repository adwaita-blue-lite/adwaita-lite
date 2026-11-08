/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <glib.h>

#include "toplevel.h"

static PinnedApp *pin(const char *name, const char *desktop_id,
    const char *app_id, const char *startup_wm_class, const char *command) {
  PinnedApp *app = g_new0(PinnedApp, 1);
  app->name = g_strdup(name);
  app->desktop_id = g_strdup(desktop_id);
  app->app_id = g_strdup(app_id);
  app->startup_wm_class = g_strdup(startup_wm_class);
  app->command = g_strdup(command);
  app->icon = g_strdup("application-x-executable");
  return app;
}

static PanelConfig *config_with_pins(PinnedApp **pins, guint count) {
  PanelConfig *config = panel_config_load_defaults();
  for (guint i = 0; i < count; i++) g_ptr_array_add(config->pinned, pins[i]);
  return config;
}

static void assert_group_order(ToplevelService *service, const char *first,
    const char *second) {
  g_assert_cmpuint(toplevel_service_test_group_count(service), ==, 2);
  g_assert_cmpstr(toplevel_service_test_group_at(service, 0)->app_id, ==, first);
  g_assert_cmpstr(toplevel_service_test_group_at(service, 1)->app_id, ==, second);
}

static void test_pin_order_survives_events(void) {
  PinnedApp *alpha = pin("Alpha", "org.example.Alpha.desktop",
      "org.example.Alpha", "AlphaStartup", "alpha-run");
  PinnedApp *beta = pin("Beta", "", "org.example.Beta", "BetaStartup", "beta-run");
  PinnedApp *pins[] = {alpha, beta};
  PanelConfig *config = config_with_pins(pins, 2);
  ToplevelService *service = toplevel_service_new_for_test();
  toplevel_service_test_set_config(service, config);

  PanelToplevel *beta_window = toplevel_service_test_add_window(service,
      "org.example.Beta", "Beta window", TRUE);
  toplevel_service_test_rebuild(service);

  g_assert_cmpuint(toplevel_service_test_group_count(service), ==, 2);
  AppGroup *alpha_group = toplevel_service_test_group_at(service, 0);
  AppGroup *beta_group = toplevel_service_test_group_at(service, 1);
  g_assert_cmpstr(alpha_group->app_id, ==, "org.example.Alpha");
  g_assert_cmpstr(beta_group->app_id, ==, "org.example.Beta");
  g_assert_true(alpha_group->pinned);
  g_assert_true(beta_group->pinned);
  g_assert_cmpuint(alpha_group->windows->len, ==, 0);
  g_assert_cmpuint(beta_group->windows->len, ==, 1);
  g_assert_true(beta_group->focused);

  /* Title and activation events must not re-create groups or reorder them. */
  toplevel_service_test_set_window_title(beta_window, "Beta renamed");
  toplevel_service_test_set_window_activated(beta_window, FALSE);
  toplevel_service_test_rebuild(service);
  assert_group_order(service, "org.example.Alpha", "org.example.Beta");
  g_assert_true(toplevel_service_test_group_at(service, 0) == alpha_group);
  g_assert_true(toplevel_service_test_group_at(service, 1) == beta_group);
  g_assert_false(beta_group->focused);
  g_assert_cmpuint(beta_group->windows->len, ==, 1);

  /* A running window must merge into its pin by any advertised identity
   * (here: startup WM class), not create an unpinned duplicate. */
  toplevel_service_test_add_window(service, "AlphaStartup", "Alpha window", FALSE);
  toplevel_service_test_rebuild(service);
  assert_group_order(service, "org.example.Alpha", "org.example.Beta");
  g_assert_true(toplevel_service_test_group_at(service, 0) == alpha_group);
  g_assert_cmpuint(alpha_group->windows->len, ==, 1);
  g_assert_cmpuint(beta_group->windows->len, ==, 1);

  /* Reordering settings moves the same group objects, preserving identity. */
  PanelConfig *reordered = panel_config_load_defaults();
  g_ptr_array_add(reordered->pinned, pin("Beta", "", "org.example.Beta",
      "BetaStartup", "beta-run"));
  g_ptr_array_add(reordered->pinned, pin("Alpha", "org.example.Alpha.desktop",
      "org.example.Alpha", "AlphaStartup", "alpha-run"));
  toplevel_service_test_set_config(service, reordered);
  panel_config_free(config);
  toplevel_service_test_rebuild(service);
  assert_group_order(service, "org.example.Beta", "org.example.Alpha");
  g_assert_true(toplevel_service_test_group_at(service, 0) == beta_group);
  g_assert_true(toplevel_service_test_group_at(service, 1) == alpha_group);

  toplevel_service_free(service);
  panel_config_free(reordered);
}

static void test_conflicting_pins_keep_window_unpinned(void) {
  PinnedApp *first = pin("Dup one", "", "org.example.Dup", "", "dup-one");
  PinnedApp *second = pin("Dup two", "", "org.example.Dup", "", "dup-two");
  PinnedApp *pins[] = {first, second};
  PanelConfig *config = config_with_pins(pins, 2);
  ToplevelService *service = toplevel_service_new_for_test();
  toplevel_service_test_set_config(service, config);

  toplevel_service_test_rebuild(service);
  g_assert_cmpuint(toplevel_service_test_group_count(service), ==, 2);
  g_assert_cmpstr(toplevel_service_test_group_at(service, 0)->name, ==, "Dup one");
  g_assert_cmpstr(toplevel_service_test_group_at(service, 1)->name, ==, "Dup two");

  toplevel_service_test_add_window(service, "org.example.Dup", "Dup window", TRUE);
  toplevel_service_test_rebuild(service);
  g_assert_cmpuint(toplevel_service_test_group_count(service), ==, 3);
  AppGroup *running = toplevel_service_test_group_at(service, 2);
  g_assert_false(running->pinned);
  g_assert_cmpuint(running->windows->len, ==, 1);
  g_assert_cmpuint(toplevel_service_test_group_at(service, 0)->windows->len, ==, 0);
  g_assert_cmpuint(toplevel_service_test_group_at(service, 1)->windows->len, ==, 0);

  toplevel_service_free(service);
  panel_config_free(config);
}

static void test_removed_pin_becomes_running_group(void) {
  PinnedApp *alpha = pin("Alpha", "org.example.Alpha.desktop",
      "org.example.Alpha", "AlphaStartup", "alpha-run");
  PinnedApp *pins[] = {alpha};
  PanelConfig *config = config_with_pins(pins, 1);
  ToplevelService *service = toplevel_service_new_for_test();
  toplevel_service_test_set_config(service, config);
  toplevel_service_test_add_window(service, "AlphaStartup", "Alpha window", TRUE);
  toplevel_service_test_rebuild(service);
  g_assert_cmpuint(toplevel_service_test_group_count(service), ==, 1);
  g_assert_cmpuint(toplevel_service_test_group_at(service, 0)->windows->len, ==, 1);

  PanelConfig *without_pins = panel_config_load_defaults();
  toplevel_service_test_set_config(service, without_pins);
  panel_config_free(config);
  toplevel_service_test_rebuild(service);
  g_assert_cmpuint(toplevel_service_test_group_count(service), ==, 1);
  AppGroup *group = toplevel_service_test_group_at(service, 0);
  g_assert_false(group->pinned);
  g_assert_cmpuint(group->windows->len, ==, 1);

  toplevel_service_free(service);
  panel_config_free(without_pins);
}

static void test_output_filtering(void) {
  PinnedApp *alpha = pin("Alpha", "org.example.Alpha.desktop",
      "org.example.Alpha", "AlphaStartup", "alpha-run");
  PinnedApp *pins[] = {alpha};
  PanelConfig *config = config_with_pins(pins, 1);
  ToplevelService *service = toplevel_service_new_for_test();
  toplevel_service_test_set_config(service, config);

  struct wl_output *output_a = (struct wl_output *)(guintptr)1;
  struct wl_output *output_b = (struct wl_output *)(guintptr)2;
  PanelToplevel *beta = toplevel_service_test_add_window(service,
      "org.example.Beta", "Beta window", TRUE);
  toplevel_service_test_add_window_output(beta, output_a);
  toplevel_service_test_add_window(service, "org.example.Late", "Late window", FALSE);
  toplevel_service_test_rebuild(service);

  AppGroup *alpha_group = toplevel_service_test_group_at(service, 0);
  AppGroup *beta_group = toplevel_service_test_group_at(service, 1);
  AppGroup *late_group = toplevel_service_test_group_at(service, 2);
  g_assert_true(toplevel_group_on_output(alpha_group, output_a));
  g_assert_true(toplevel_group_on_output(alpha_group, output_b));
  g_assert_true(toplevel_group_on_output(beta_group, output_a));
  g_assert_false(toplevel_group_on_output(beta_group, output_b));
  /* Late output metadata stays visible everywhere. */
  g_assert_true(toplevel_group_on_output(late_group, output_b));

  toplevel_service_free(service);
  panel_config_free(config);
}

static void test_default_layout(void) {
  PanelConfig *config = panel_config_load_defaults();
  g_assert_cmpuint(config->layout_start->len, ==, 1);
  g_assert_cmpstr(g_ptr_array_index(config->layout_start, 0), ==, "custom/launcher");
  g_assert_cmpuint(config->layout_center->len, ==, 1);
  g_assert_cmpstr(g_ptr_array_index(config->layout_center, 0), ==, "wlr/taskbar");
  g_assert_cmpuint(config->layout_end->len, ==, 5);
  g_assert_cmpstr(g_ptr_array_index(config->layout_end, 0), ==, "pulseaudio");
  g_assert_cmpstr(g_ptr_array_index(config->layout_end, 4), ==, "tray");
  panel_config_free(config);
}

static void test_close_window_frees_once(void) {
  PanelConfig *config = panel_config_load_defaults();
  ToplevelService *service = toplevel_service_new_for_test();
  toplevel_service_test_set_config(service, config);
  PanelToplevel *first = toplevel_service_test_add_window(service,
      "org.example.First", "First", TRUE);
  PanelToplevel *second = toplevel_service_test_add_window(service,
      "org.example.Second", "Second", FALSE);
  toplevel_service_test_rebuild(service);
  g_assert_cmpuint(toplevel_service_test_group_count(service), ==, 2);

  toplevel_service_test_close_window(first);
  g_assert_cmpuint(toplevel_service_test_group_count(service), ==, 1);
  toplevel_service_test_close_window(second);
  g_assert_cmpuint(toplevel_service_test_group_count(service), ==, 0);

  toplevel_service_free(service);
  panel_config_free(config);
}

int main(int argc, char **argv) {
  g_test_init(&argc, &argv, NULL);
  g_test_add_func("/toplevel/default-layout", test_default_layout);
  g_test_add_func("/toplevel/close-window-frees-once",
      test_close_window_frees_once);
  g_test_add_func("/toplevel/pin-order-survives-events",
      test_pin_order_survives_events);
  g_test_add_func("/toplevel/conflicting-pins-stay-unpinned",
      test_conflicting_pins_keep_window_unpinned);
  g_test_add_func("/toplevel/removed-pin-becomes-running",
      test_removed_pin_becomes_running_group);
  g_test_add_func("/toplevel/output-filtering", test_output_filtering);
  return g_test_run();
}
