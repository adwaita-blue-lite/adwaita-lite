/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "audio.h"

#include <string.h>

#define REFRESH_MS 30
#define WRITE_MS 40
#define STEP_POINTS 5

struct _PanelAudio {
  pa_glib_mainloop *mainloop;
  pa_context *context;
  PanelAudioNotify notify;
  gpointer notify_data;

  pa_cvolume volume;
  gboolean have_volume;
  gboolean muted;
  char *sink_name;
  uint32_t sink_index;
  PanelAudioStatus status;
  gboolean dead;
  guint refresh_source;
  guint retry_source;
  guint write_source;
  guint retry_delay;
  pa_cvolume pending;
  gboolean pending_valid;
};

static int percent_of(const pa_cvolume *volume) {
  if (!volume || volume->channels == 0 || !pa_cvolume_valid(volume)) return 0;
  guint64 avg = pa_cvolume_avg(volume);
  return (int)((avg * 100 + PA_VOLUME_NORM / 2) / PA_VOLUME_NORM);
}

int panel_audio_percent(const pa_cvolume *volume) {
  return percent_of(volume);
}

static pa_volume_t tick_for(int points) {
  return (pa_volume_t)(((guint64)PA_VOLUME_NORM * points + 50) / 100);
}

void panel_audio_apply_step(pa_cvolume *volume, int delta_points) {
  if (!volume || volume->channels == 0 || !pa_cvolume_valid(volume) || delta_points == 0)
    return;
  int current = percent_of(volume);
  if (delta_points > 0 && current >= 100) return;
  if (delta_points < 0 && current <= 0) return;

  int points = delta_points > 0 ? MIN(delta_points, 100 - current)
                                : -MIN(-delta_points, current);
  pa_volume_t change = tick_for(points < 0 ? -points : points);
  for (unsigned channel = 0; channel < volume->channels; channel++) {
    if (points > 0) {
      guint64 next = (guint64)volume->values[channel] + change;
      volume->values[channel] = (pa_volume_t)MIN(next, (guint64)PA_VOLUME_MAX);
    } else {
      volume->values[channel] = volume->values[channel] > change
          ? volume->values[channel] - change : PA_VOLUME_MUTED;
    }
  }
}

static void emit(PanelAudio *self) {
  if (self->notify) self->notify(self->notify_data);
}

static void schedule_reconnect(PanelAudio *self);
static void schedule_refresh(PanelAudio *self);

static void sink_info_cb(pa_context *context, const pa_sink_info *info, int eol,
    void *data) {
  PanelAudio *self = data;
  if (self->dead) return;
  if (eol < 0) {
    if (pa_context_errno(context) == PA_ERR_NOENTITY) {
      self->status = AUDIO_NO_SINK;
      self->have_volume = FALSE;
      g_clear_pointer(&self->sink_name, g_free);
      emit(self);
    }
    return;
  }
  if (eol > 0 || !info || !pa_cvolume_valid(&info->volume) ||
      info->volume.channels == 0)
    return;

  gboolean changed = !self->have_volume ||
      !pa_cvolume_equal(&self->volume, &info->volume) ||
      self->muted != info->mute ||
      g_strcmp0(self->sink_name, info->name) != 0;

  self->volume = info->volume;
  self->have_volume = TRUE;
  self->muted = info->mute;
  g_free(self->sink_name);
  self->sink_name = g_strdup(info->name);
  self->sink_index = info->index;
  self->status = AUDIO_READY;
  if (changed) emit(self);
}

static gboolean refresh_cb(gpointer data) {
  PanelAudio *self = data;
  self->refresh_source = 0;
  if (self->dead || !self->context ||
      pa_context_get_state(self->context) != PA_CONTEXT_READY)
    return G_SOURCE_REMOVE;
  pa_operation *op = pa_context_get_sink_info_by_name(
      self->context, "@DEFAULT_SINK@", sink_info_cb, self);
  if (op) pa_operation_unref(op);
  else emit(self);
  return G_SOURCE_REMOVE;
}

static void schedule_refresh(PanelAudio *self) {
  if (self->dead || self->refresh_source) return;
  self->refresh_source = g_timeout_add(REFRESH_MS, refresh_cb, self);
}

static void subscription_cb(pa_context *context, pa_subscription_event_type_t type,
    uint32_t index, void *data) {
  (void)context;
  PanelAudio *self = data;
  unsigned facility = type & PA_SUBSCRIPTION_EVENT_FACILITY_MASK;
  unsigned event = type & PA_SUBSCRIPTION_EVENT_TYPE_MASK;

  if (facility == PA_SUBSCRIPTION_EVENT_SERVER &&
      event == PA_SUBSCRIPTION_EVENT_CHANGE) {
    schedule_refresh(self);
  } else if (facility == PA_SUBSCRIPTION_EVENT_SINK) {
    if (event == PA_SUBSCRIPTION_EVENT_CHANGE) {
      if (index == self->sink_index) schedule_refresh(self);
    } else if (event == PA_SUBSCRIPTION_EVENT_NEW ||
               event == PA_SUBSCRIPTION_EVENT_REMOVE) {
      schedule_refresh(self);
    }
  }
}

static void set_done_cb(pa_context *context, int success, void *data) {
  (void)context;
  PanelAudio *self = data;
  if (!self->dead && !success) schedule_refresh(self);
}

static gboolean write_cb(gpointer data) {
  PanelAudio *self = data;
  self->write_source = 0;
  if (self->dead || !self->pending_valid) return G_SOURCE_REMOVE;

  pa_cvolume volume = self->pending;
  self->pending_valid = FALSE;
  if (!self->sink_name || !self->context ||
      pa_context_get_state(self->context) != PA_CONTEXT_READY) {
    schedule_refresh(self);
    return G_SOURCE_REMOVE;
  }
  pa_operation *op = pa_context_set_sink_volume_by_name(
      self->context, self->sink_name, &volume, set_done_cb, self);
  if (op) pa_operation_unref(op);
  else schedule_refresh(self);
  return G_SOURCE_REMOVE;
}

void panel_audio_step(PanelAudio *self, int delta_points) {
  if (!self || self->dead || self->status != AUDIO_READY || !self->have_volume)
    return;
  int before = percent_of(&self->volume);
  pa_cvolume next = self->volume;
  panel_audio_apply_step(&next, delta_points);
  if (percent_of(&next) == before) return;

  self->volume = next;
  emit(self);
  self->pending = next;
  self->pending_valid = TRUE;
  if (!self->write_source)
    self->write_source = g_timeout_add(WRITE_MS, write_cb, self);
}

static gboolean retry_cb(gpointer data);

static void schedule_reconnect(PanelAudio *self) {
  if (self->dead || self->retry_source) return;
  self->retry_source = g_timeout_add_seconds(self->retry_delay, retry_cb, self);
  self->retry_delay = MIN(self->retry_delay * 2, 30);
}

static void state_cb(pa_context *context, void *data) {
  PanelAudio *self = data;
  pa_context_state_t state = pa_context_get_state(context);
  if (state == PA_CONTEXT_READY) {
    self->retry_delay = 1;
    self->status = AUDIO_CONNECTING;
    pa_context_set_subscribe_callback(context, subscription_cb, self);
    pa_operation *op = pa_context_subscribe(context,
        PA_SUBSCRIPTION_MASK_SINK | PA_SUBSCRIPTION_MASK_SERVER, NULL, NULL);
    if (op) pa_operation_unref(op);
    schedule_refresh(self);
    emit(self);
  } else if (state == PA_CONTEXT_FAILED || state == PA_CONTEXT_TERMINATED) {
    if (self->dead) return;
    self->status = AUDIO_UNAVAILABLE;
    self->have_volume = FALSE;
    g_clear_pointer(&self->sink_name, g_free);
    emit(self);
    schedule_reconnect(self);
  }
}

static void start_context(PanelAudio *self) {
  if (self->dead) return;
  if (self->context) {
    pa_context_set_state_callback(self->context, NULL, NULL);
    pa_context_set_subscribe_callback(self->context, NULL, NULL);
    pa_context_disconnect(self->context);
    pa_context_unref(self->context);
    self->context = NULL;
  }
  self->context = pa_context_new(pa_glib_mainloop_get_api(self->mainloop),
      "adwaita-lite-panel");
  if (!self->context) {
    schedule_reconnect(self);
    return;
  }
  pa_context_set_state_callback(self->context, state_cb, self);
  pa_context_connect(self->context, NULL, PA_CONTEXT_NOAUTOSPAWN, NULL);
}

static gboolean retry_cb(gpointer data) {
  PanelAudio *self = data;
  self->retry_source = 0;
  if (!self->dead) start_context(self);
  return G_SOURCE_REMOVE;
}

PanelAudio *panel_audio_new(PanelAudioNotify notify, gpointer data) {
  PanelAudio *self = g_new0(PanelAudio, 1);
  self->notify = notify;
  self->notify_data = data;
  self->status = AUDIO_CONNECTING;
  self->retry_delay = 1;
  return self;
}

void panel_audio_start(PanelAudio *self) {
  if (!self || self->mainloop) return;
  self->mainloop = pa_glib_mainloop_new(NULL);
  if (!self->mainloop) {
    self->status = AUDIO_UNAVAILABLE;
    emit(self);
    return;
  }
  start_context(self);
}

void panel_audio_get_state(PanelAudio *self, PanelAudioState *out) {
  out->status = self ? self->status : AUDIO_UNAVAILABLE;
  out->muted = self ? self->muted : FALSE;
  out->percent = (self && self->have_volume) ? percent_of(&self->volume) : 0;
}

void panel_audio_free(PanelAudio *self) {
  if (!self) return;
  self->dead = TRUE;
  if (self->refresh_source) g_source_remove(self->refresh_source);
  if (self->retry_source) g_source_remove(self->retry_source);
  if (self->write_source) g_source_remove(self->write_source);
  if (self->context) {
    pa_context_set_state_callback(self->context, NULL, NULL);
    pa_context_set_subscribe_callback(self->context, NULL, NULL);
    pa_context_disconnect(self->context);
    pa_context_unref(self->context);
  }
  if (self->mainloop) pa_glib_mainloop_free(self->mainloop);
  g_free(self->sink_name);
  g_free(self);
}
