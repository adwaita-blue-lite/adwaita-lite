/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "status.h"

#include <gio/gio.h>
#include <string.h>

#define UP_NAME "org.freedesktop.UPower"
#define UP_PATH "/org/freedesktop/UPower/devices/DisplayDevice"
#define UP_IFACE "org.freedesktop.UPower.Device"
#define NM_NAME "org.freedesktop.NetworkManager"
#define NM_PATH "/org/freedesktop/NetworkManager"
#define NM_IFACE "org.freedesktop.NetworkManager"

static void status_unref(PanelStatus *self);

struct _PanelStatus {
  gint refs;
  gboolean dead;
  PanelConfig *config;
  void (*changed)(gpointer);
  gpointer changed_data;
  GCancellable *cancel;

  guint up_watch;
  GDBusProxy *up_device;

  guint nm_watch;
  GDBusProxy *nm_manager;

  gboolean battery_visible;
  int battery_percent;
  int battery_severity;
  char battery_icon[64];
  char *battery_tooltip;
  char *battery_label;

  gboolean network_visible;
  char network_icon[64];
  char *network_tooltip;
  char *network_label;

  gboolean backlight_visible;
  char *backlight_dir;
  char *backlight_name;
  guint backlight_max;
  char backlight_tooltip[64];
};

static void status_unref(PanelStatus *self) {
  if (g_atomic_int_dec_and_test(&self->refs)) g_free(self);
}

static PanelStatus *status_ref(PanelStatus *self) {
  g_atomic_int_inc(&self->refs);
  return self;
}

static GVariant *cached(GDBusProxy *proxy, const char *name) {
  return proxy ? g_dbus_proxy_get_cached_property(proxy, name) : NULL;
}

static guint cached_u32(GDBusProxy *proxy, const char *name, guint fallback) {
  GVariant *value = cached(proxy, name);
  if (!value) return fallback;
  guint out = g_variant_get_uint32(value);
  g_variant_unref(value);
  return out;
}

static gboolean cached_bool(GDBusProxy *proxy, const char *name) {
  GVariant *value = cached(proxy, name);
  if (!value) return FALSE;
  gboolean out = g_variant_get_boolean(value);
  g_variant_unref(value);
  return out;
}

static guint cached_percent(GDBusProxy *proxy, const char *name) {
  GVariant *value = cached(proxy, name);
  if (!value) return 0;
  double out = g_variant_get_double(value);
  g_variant_unref(value);
  return (guint)(out + 0.5);
}

static gchar *cached_str(GDBusProxy *proxy, const char *name) {
  GVariant *value = cached(proxy, name);
  if (!value) return NULL;
  gchar *out = g_variant_dup_string(value, NULL);
  g_variant_unref(value);
  return out;
}

static gboolean read_uint(const char *path, guint *out) {
  char *text = NULL;
  if (!g_file_get_contents(path, &text, NULL, NULL)) return FALSE;
  guint64 value = g_ascii_strtoull(text, NULL, 10);
  g_free(text);
  if (value > G_MAXUINT) return FALSE;
  *out = (guint)value;
  return TRUE;
}

static void notify(PanelStatus *self) {
  if (!self->dead && self->changed) self->changed(self->changed_data);
}

static void battery_icon(char *buffer, size_t size, guint percent, guint state) {
  gboolean charging = state == 1 || state == 5;
  gboolean full = state == 4;
  guint level = percent >= 100 ? 100 : ((percent + 9) / 10) * 10;
  if (full) {
    g_snprintf(buffer, size, "battery-level-100-charged-symbolic");
  } else if (level == 100 && charging) {
    g_snprintf(buffer, size, "battery-level-100-plugged-in-symbolic");
  } else {
    g_snprintf(buffer, size, "battery-level-%u%s-symbolic", level,
        charging ? "-charging" : "");
  }
}

static void power_reload(PanelStatus *self) {
  if (self->dead) return;
  if (!self->up_device) {
    self->battery_visible = FALSE;
    notify(self);
    return;
  }

  guint type = cached_u32(self->up_device, "Type", 0);
  gboolean present = cached_bool(self->up_device, "IsPresent");
  if (!present || type != 2) {
    self->battery_visible = FALSE;
    notify(self);
    return;
  }

  guint percent = cached_percent(self->up_device, "Percentage");
  guint state = cached_u32(self->up_device, "State", 0);
  gboolean charging = state == 1 || state == 4 || state == 5;

  self->battery_visible = TRUE;
  self->battery_percent = (int)percent;
  self->battery_severity = (!charging && percent < 12) ? 2 :
      (!charging && percent < 25) ? 1 : 0;
  battery_icon(self->battery_icon, sizeof self->battery_icon, percent, state);

  g_free(self->battery_tooltip);
  self->battery_tooltip = g_strdup_printf("%u%%", percent);
  g_free(self->battery_label);
  const char *state_text = charging ? "charging" : "discharging";
  self->battery_label = g_strdup_printf("Battery, %u percent, %s", percent, state_text);
  notify(self);
}

static void up_props(GDBusProxy *proxy, GVariant *changed,
    const gchar *const *invalidated, gpointer data) {
  (void)proxy; (void)changed; (void)invalidated;
  power_reload(data);
}

static void up_ready(GObject *source, GAsyncResult *result, gpointer data) {
  (void)source;
  PanelStatus *self = data;
  GError *error = NULL;
  GDBusProxy *proxy = g_dbus_proxy_new_for_bus_finish(result, &error);
  if (!proxy) {
    g_clear_error(&error);
    self->battery_visible = FALSE;
    notify(self);
    status_unref(self);
    return;
  }
  if (self->dead) {
    g_object_unref(proxy);
    status_unref(self);
    return;
  }
  g_clear_object(&self->up_device);
  self->up_device = proxy;
  g_signal_connect(proxy, "g-properties-changed", G_CALLBACK(up_props), self);
  power_reload(self);
  status_unref(self);
}

static void up_appeared(GDBusConnection *connection, const gchar *name,
    const gchar *owner, gpointer data) {
  (void)connection; (void)name; (void)owner;
  PanelStatus *self = data;
  g_dbus_proxy_new_for_bus(G_BUS_TYPE_SYSTEM,
      G_DBUS_PROXY_FLAGS_DO_NOT_AUTO_START |
      G_DBUS_PROXY_FLAGS_GET_INVALIDATED_PROPERTIES,
      NULL, UP_NAME, UP_PATH, UP_IFACE, self->cancel, up_ready, status_ref(self));
}

static void up_vanished(GDBusConnection *connection, const gchar *name, gpointer data) {
  (void)connection; (void)name;
  PanelStatus *self = data;
  g_clear_object(&self->up_device);
  self->battery_visible = FALSE;
  notify(self);
}

static void net_reload(PanelStatus *self) {
  if (self->dead) return;
  if (!self->config->panel_network || !self->nm_manager) {
    self->network_visible = FALSE;
    notify(self);
    return;
  }

  guint state = cached_u32(self->nm_manager, "State", 0);
  gchar *primary = cached_str(self->nm_manager, "PrimaryConnection");
  gchar *type = cached_str(self->nm_manager, "PrimaryConnectionType");
  gboolean connected = state == 70 && primary && strcmp(primary, "/") != 0;

  self->network_visible = TRUE;
  if (!connected) {
    g_strlcpy(self->network_icon, "network-offline-symbolic", sizeof self->network_icon);
    g_free(self->network_tooltip); self->network_tooltip = g_strdup("Offline");
    g_free(self->network_label); self->network_label = g_strdup("Network, offline");
  } else if (type && strstr(type, "wireless")) {
    g_strlcpy(self->network_icon, "network-wireless-signal-good-symbolic",
        sizeof self->network_icon);
    g_free(self->network_tooltip); self->network_tooltip = g_strdup("Wi-Fi");
    g_free(self->network_label); self->network_label = g_strdup("Network, Wi-Fi connected");
  } else {
    g_strlcpy(self->network_icon, "network-wired-symbolic", sizeof self->network_icon);
    g_free(self->network_tooltip); self->network_tooltip = g_strdup("Wired");
    g_free(self->network_label); self->network_label = g_strdup("Network, wired connected");
  }
  g_free(primary);
  g_free(type);
  notify(self);
}

static void nm_props(GDBusProxy *proxy, GVariant *changed,
    const gchar *const *invalidated, gpointer data) {
  (void)proxy; (void)changed; (void)invalidated;
  net_reload(data);
}

static void nm_ready(GObject *source, GAsyncResult *result, gpointer data) {
  (void)source;
  PanelStatus *self = data;
  GError *error = NULL;
  GDBusProxy *proxy = g_dbus_proxy_new_for_bus_finish(result, &error);
  if (!proxy) {
    g_clear_error(&error);
    status_unref(self);
    return;
  }
  if (self->dead || !self->config->panel_network) {
    g_object_unref(proxy);
    status_unref(self);
    return;
  }
  g_clear_object(&self->nm_manager);
  self->nm_manager = proxy;
  g_signal_connect(proxy, "g-properties-changed", G_CALLBACK(nm_props), self);
  net_reload(self);
  status_unref(self);
}

static void nm_appeared(GDBusConnection *connection, const gchar *name,
    const gchar *owner, gpointer data) {
  (void)connection; (void)name; (void)owner;
  PanelStatus *self = data;
  if (!self->config->panel_network) return;
  g_dbus_proxy_new_for_bus(G_BUS_TYPE_SYSTEM,
      G_DBUS_PROXY_FLAGS_DO_NOT_AUTO_START |
      G_DBUS_PROXY_FLAGS_GET_INVALIDATED_PROPERTIES,
      NULL, NM_NAME, NM_PATH, NM_IFACE, self->cancel, nm_ready, status_ref(self));
}

static void nm_vanished(GDBusConnection *connection, const gchar *name, gpointer data) {
  (void)connection; (void)name;
  PanelStatus *self = data;
  g_clear_object(&self->nm_manager);
  self->network_visible = FALSE;
  notify(self);
}

static void backlight_clear(PanelStatus *self) {
  g_free(self->backlight_dir);
  g_free(self->backlight_name);
  self->backlight_dir = NULL;
  self->backlight_name = NULL;
  self->backlight_max = 0;
  self->backlight_visible = FALSE;
}

static void backlight_scan(PanelStatus *self) {
  backlight_clear(self);
  const char *root = g_getenv("ADWAITA_LITE_SYSFS_ROOT");
  char *base = g_build_filename(root ? root : "/", "sys/class/backlight", NULL);
  GDir *dir = g_dir_open(base, 0, NULL);
  if (!dir) {
    g_free(base);
    return;
  }

  char *best = NULL;
  int best_rank = -1;
  guint best_max = 0;
  const char *name;
  while ((name = g_dir_read_name(dir))) {
    char *device = g_build_filename(base, name, NULL);
    char *type_path = g_build_filename(device, "type", NULL);
    char *max_path = g_build_filename(device, "max_brightness", NULL);
    char *type = NULL;
    guint max = 0;
    if (g_file_get_contents(type_path, &type, NULL, NULL) &&
        read_uint(max_path, &max) && max > 0) {
      int rank = strstr(type, "firmware") ? 2 : strstr(type, "platform") ? 1 : 0;
      if (rank > best_rank || (rank == best_rank && max > best_max)) {
        g_free(best);
        best = g_strdup(name);
        best_rank = rank;
        best_max = max;
      }
    }
    g_free(type);
    g_free(type_path);
    g_free(max_path);
    g_free(device);
  }
  g_dir_close(dir);
  g_free(base);

  if (!best) return;
  self->backlight_name = best;
  self->backlight_dir = g_build_filename("/sys/class/backlight", best, NULL);
  if (root) {
    g_free(self->backlight_dir);
    self->backlight_dir = g_build_filename(root, "sys/class/backlight", best, NULL);
  }
  self->backlight_max = best_max;
  self->backlight_visible = TRUE;
}

static int backlight_percent(PanelStatus *self) {
  if (!self->backlight_visible || !self->backlight_dir || !self->backlight_max)
    return 0;
  char *path = g_build_filename(self->backlight_dir, "brightness", NULL);
  guint value = 0;
  if (!read_uint(path, &value)) {
    g_free(path);
    path = g_build_filename(self->backlight_dir, "actual_brightness", NULL);
    read_uint(path, &value);
  }
  g_free(path);
  return (int)(((guint64)value * 100 + self->backlight_max / 2) / self->backlight_max);
}

PanelStatus *panel_status_new(PanelConfig *config,
    void (*changed)(gpointer), gpointer data) {
  PanelStatus *self = g_new0(PanelStatus, 1);
  self->refs = 1;
  self->config = config;
  self->changed = changed;
  self->changed_data = data;
  self->cancel = g_cancellable_new();

  self->up_watch = g_bus_watch_name(G_BUS_TYPE_SYSTEM, UP_NAME,
      G_BUS_NAME_WATCHER_FLAGS_NONE, up_appeared, up_vanished, self, NULL);
  if (config->panel_network) {
    self->nm_watch = g_bus_watch_name(G_BUS_TYPE_SYSTEM, NM_NAME,
        G_BUS_NAME_WATCHER_FLAGS_NONE, nm_appeared, nm_vanished, self, NULL);
  }
  backlight_scan(self);
  return self;
}

void panel_status_set_config(PanelStatus *self, PanelConfig *config) {
  if (!self) return;
  self->config = config;
  if (config->panel_network && !self->nm_watch) {
    self->nm_watch = g_bus_watch_name(G_BUS_TYPE_SYSTEM, NM_NAME,
        G_BUS_NAME_WATCHER_FLAGS_NONE, nm_appeared, nm_vanished, self, NULL);
  } else if (!config->panel_network) {
    if (self->nm_watch) {
      g_bus_unwatch_name(self->nm_watch);
      self->nm_watch = 0;
    }
    g_clear_object(&self->nm_manager);
    self->network_visible = FALSE;
  }
  backlight_scan(self);
  if (self->nm_manager) net_reload(self);
  else notify(self);
}

void panel_status_get(PanelStatus *self, PanelBatteryView *battery,
    PanelNetworkView *network, PanelBacklightView *backlight) {
  if (battery) {
    battery->visible = self->battery_visible;
    battery->percent = self->battery_percent;
    battery->icon = self->battery_icon;
    battery->tooltip = self->battery_tooltip;
    battery->label = self->battery_label;
    battery->severity = self->battery_severity;
  }
  if (network) {
    network->visible = self->network_visible;
    network->icon = self->network_icon;
    network->tooltip = self->network_tooltip;
    network->label = self->network_label;
  }
  if (backlight) {
    backlight->visible = self->backlight_visible;
    backlight->percent = self->backlight_visible ? backlight_percent(self) : 0;
    g_snprintf(self->backlight_tooltip, sizeof self->backlight_tooltip,
        "%d%%", backlight->percent);
    backlight->tooltip = self->backlight_tooltip;
  }
}

void panel_status_free(PanelStatus *self) {
  if (!self) return;
  self->dead = TRUE;
  if (self->cancel) g_cancellable_cancel(self->cancel);
  if (self->up_watch) g_bus_unwatch_name(self->up_watch);
  if (self->nm_watch) g_bus_unwatch_name(self->nm_watch);
  g_clear_object(&self->up_device);
  g_clear_object(&self->nm_manager);
  g_clear_object(&self->cancel);
  g_free(self->battery_tooltip);
  g_free(self->battery_label);
  g_free(self->network_tooltip);
  g_free(self->network_label);
  backlight_clear(self);
  status_unref(self);
}
