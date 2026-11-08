/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <glib.h>

#include "shelf.h"

static void pump(guint milliseconds) {
  gint64 deadline = g_get_monotonic_time() + (gint64)milliseconds * 1000;
  while (g_get_monotonic_time() < deadline) {
    while (g_main_context_iteration(NULL, FALSE));
    g_usleep(1000);
  }
}

/* A settings reload frees the PanelWindow while the 500 ms ON_DEMAND
 * timeout may still be pending. The timeout must be cancelled on free and
 * must never run against freed memory. */
static void test_keyboard_timeout_cancelled_on_free(void) {
  guint before = panel_window_keyboard_fires_for_test();
  PanelWindow *window = panel_window_new_for_test();
  guint source = panel_window_arm_keyboard_for_test(window, 30);
  g_assert_cmpuint(source, !=, 0);
  panel_window_free_for_test(window);
  pump(120);
  g_assert_cmpuint(panel_window_keyboard_fires_for_test(), ==, before);
}

static void test_keyboard_timeout_fires_when_live(void) {
  guint before = panel_window_keyboard_fires_for_test();
  PanelWindow *window = panel_window_new_for_test();
  panel_window_arm_keyboard_for_test(window, 20);
  pump(150);
  g_assert_cmpuint(panel_window_keyboard_fires_for_test(), ==, before + 1);
  g_assert_true(panel_window_keyboard_mode_for_test(window));
  panel_window_free_for_test(window);
}

static void test_keyboard_timeout_rearm_cancels_previous(void) {
  guint before = panel_window_keyboard_fires_for_test();
  PanelWindow *window = panel_window_new_for_test();
  panel_window_arm_keyboard_for_test(window, 80);
  panel_window_arm_keyboard_for_test(window, 20);
  pump(160);
  g_assert_cmpuint(panel_window_keyboard_fires_for_test(), ==, before + 1);
  panel_window_free_for_test(window);
}

int main(int argc, char **argv) {
  g_test_init(&argc, &argv, NULL);
  g_test_add_func("/shelf/keyboard-timeout-cancelled-on-free",
      test_keyboard_timeout_cancelled_on_free);
  g_test_add_func("/shelf/keyboard-timeout-fires",
      test_keyboard_timeout_fires_when_live);
  g_test_add_func("/shelf/keyboard-timeout-rearm",
      test_keyboard_timeout_rearm_cancels_previous);
  return g_test_run();
}
