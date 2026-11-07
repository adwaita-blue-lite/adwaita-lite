/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once

#include <gtk/gtk.h>

#include "config.h"

typedef struct _PanelShelf PanelShelf;

PanelShelf *panel_shelf_new(GtkApplication *app, PanelConfig *config);
void panel_shelf_reload(PanelShelf *shelf, PanelConfig *config);
void panel_shelf_free(PanelShelf *shelf);
