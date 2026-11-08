/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include <glib.h>
#include <pulse/glib-mainloop.h>
#include <pulse/pulseaudio.h>

typedef enum {
  AUDIO_CONNECTING,
  AUDIO_READY,
  AUDIO_NO_SINK,
  AUDIO_UNAVAILABLE,
} PanelAudioStatus;

typedef struct {
  PanelAudioStatus status;
  gboolean muted;
  int percent;
} PanelAudioState;

typedef void (*PanelAudioNotify)(gpointer data);

typedef struct _PanelAudio PanelAudio;

PanelAudio *panel_audio_new(PanelAudioNotify notify, gpointer data);
void panel_audio_start(PanelAudio *self);
void panel_audio_free(PanelAudio *self);
void panel_audio_get_state(PanelAudio *self, PanelAudioState *out);
void panel_audio_step(PanelAudio *self, int delta_points);

int panel_audio_percent(const pa_cvolume *volume);
void panel_audio_apply_step(pa_cvolume *volume, int delta_points);
