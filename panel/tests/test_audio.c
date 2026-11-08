/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <glib.h>

#include "audio.h"

static void test_percent_and_steps(void) {
  pa_cvolume volume;
  pa_cvolume_init(&volume);
  volume.channels = 2;
  volume.values[0] = PA_VOLUME_NORM / 2;
  volume.values[1] = PA_VOLUME_NORM / 2;
  g_assert_cmpint(panel_audio_percent(&volume), ==, 50);

  panel_audio_apply_step(&volume, 5);
  g_assert_cmpint(panel_audio_percent(&volume), ==, 55);

  panel_audio_apply_step(&volume, 100);
  g_assert_cmpint(panel_audio_percent(&volume), ==, 100);

  panel_audio_apply_step(&volume, -200);
  g_assert_cmpint(panel_audio_percent(&volume), ==, 0);

  panel_audio_apply_step(&volume, -5);
  g_assert_cmpint(panel_audio_percent(&volume), ==, 0);
}

int main(int argc, char **argv) {
  g_test_init(&argc, &argv, NULL);
  g_test_add_func("/audio/steps", test_percent_and_steps);
  return g_test_run();
}
