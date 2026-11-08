/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include <gtk/gtk.h>

#include "config.h"
#include "toplevel.h"

typedef struct _PanelShelf PanelShelf;
typedef struct _PanelWindow PanelWindow;

PanelShelf *panel_shelf_new(GtkApplication *app, PanelConfig *config);
void panel_shelf_reload(PanelShelf *shelf, PanelConfig *config);
void panel_shelf_free(PanelShelf *shelf);

#ifdef PANEL_TEST
/* Headless helpers used by tests to exercise the focus/keyboard timeout
 * lifetime without creating a layer-shell window. */
PanelWindow *panel_window_new_for_test(void);
void panel_window_free_for_test(PanelWindow *window);
guint panel_window_arm_keyboard_for_test(PanelWindow *window, guint delay_ms);
gboolean panel_window_keyboard_mode_for_test(PanelWindow *window);
guint panel_window_keyboard_fires_for_test(void);
#endif
