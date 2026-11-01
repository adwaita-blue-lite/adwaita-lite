LOCALEDIR = ../files/usr/share/locale
LANGUAGES = am ar de es fa fr ha hi it ja ko nl pl pt ru sv sw th tr vi yo zh

# --- Wizard domain ---
WIZARD_DOMAIN = adwaita-lite-setup-wizard
WIZARD_SOURCE = ../files/usr/bin/$(WIZARD_DOMAIN)
WIZARD_POT = $(WIZARD_DOMAIN).pot
WIZARD_PO = $(LANGUAGES:%=%.po)
WIZARD_MO = $(LANGUAGES:%=$(LOCALEDIR)/%/LC_MESSAGES/$(WIZARD_DOMAIN).mo)

# --- Settings domain ---
SETTINGS_DOMAIN = adwaita-lite-settings
SETTINGS_POT = settings/$(SETTINGS_DOMAIN).pot
SETTINGS_PO = $(LANGUAGES:%=settings/%.po)
SETTINGS_MO = $(LANGUAGES:%=$(LOCALEDIR)/%/LC_MESSAGES/$(SETTINGS_DOMAIN).mo)

# --- App menu domain ---
APP_MENU_DOMAIN = adwaita-lite-app-menu
APP_MENU_SOURCE = ../files/usr/bin/adwaita-lite-app-menu
APP_MENU_POT = app-menu/$(APP_MENU_DOMAIN).pot
APP_MENU_PO = $(LANGUAGES:%=app-menu/%.po)
APP_MENU_MO = $(LANGUAGES:%=$(LOCALEDIR)/%/LC_MESSAGES/$(APP_MENU_DOMAIN).mo)

SETTINGS_SOURCES = \
	../files/usr/bin/adwaita-lite-settings \
	../files/usr/bin/adwaita-lite-greeter \
	../files/usr/lib/adwaita-lite/settings/app.py \
	../files/usr/lib/adwaita-lite/settings/base.py \
	../files/usr/lib/adwaita-lite/settings/dbus_helpers.py \
	../files/usr/lib/adwaita-lite/settings/settings_store.py \
	../files/usr/lib/adwaita-lite/settings/wallpapers.py \
	../files/usr/lib/adwaita-lite/settings/window.py \
	../files/usr/lib/adwaita-lite/settings/pages/__init__.py \
	$(wildcard ../files/usr/lib/adwaita-lite/settings/pages/[a-z]*.py)

.PHONY: pot po mo clean all

# --- Wizard targets ---
pot-wizard: $(WIZARD_POT)

$(WIZARD_POT): $(WIZARD_SOURCE)
	xgettext --language=Python --keyword=_ --keyword=N_ \
	    --keyword=_make_translated_label \
	    --keyword=_make_summary_row:2 \
	    --output=$(WIZARD_POT) --from-code=UTF-8 \
	    --package-name="$(WIZARD_DOMAIN)" \
	    $(WIZARD_SOURCE)

po-wizard: $(WIZARD_PO)

%.po: $(WIZARD_POT)
	@if [ -f $@ ]; then \
	    msgmerge --update --no-fuzzy-matching $@ $(WIZARD_POT); \
	else \
	    msginit --input=$(WIZARD_POT) --output=$@ --locale=$* --no-translator; \
	fi

mo-wizard: $(WIZARD_MO)

$(LOCALEDIR)/%/LC_MESSAGES/$(WIZARD_DOMAIN).mo: %.po
	@mkdir -p $(dir $@)
	msgfmt --output=$@ $<

# --- Settings targets ---
pot-settings: $(SETTINGS_POT)

$(SETTINGS_POT): $(SETTINGS_SOURCES)
	@mkdir -p settings
	xgettext --language=Python --keyword=_ --keyword=N_ \
	    --output=$(SETTINGS_POT) --from-code=UTF-8 \
	    --package-name="$(SETTINGS_DOMAIN)" \
	    $(SETTINGS_SOURCES)

po-settings: $(SETTINGS_PO)

settings/%.po: $(SETTINGS_POT)
	@mkdir -p settings
	@if [ -f $@ ]; then \
	    msgmerge --update --no-fuzzy-matching $@ $(SETTINGS_POT); \
	else \
	    msginit --input=$(SETTINGS_POT) --output=$@ --locale=$* --no-translator; \
	fi

mo-settings: $(SETTINGS_MO)

$(LOCALEDIR)/%/LC_MESSAGES/$(SETTINGS_DOMAIN).mo: settings/%.po
	@mkdir -p $(dir $@)
	msgfmt --output=$@ $<

# --- App menu targets ---
pot-app-menu: $(APP_MENU_POT)

$(APP_MENU_POT): $(APP_MENU_SOURCE)
	@mkdir -p app-menu
	xgettext --language=Python --keyword=_ --keyword=N_ \
	    --output=$(APP_MENU_POT) --from-code=UTF-8 \
	    --package-name="$(APP_MENU_DOMAIN)" \
	    $(APP_MENU_SOURCE)

po-app-menu: $(APP_MENU_PO)

app-menu/%.po: $(APP_MENU_POT)
	@mkdir -p app-menu
	@if [ -f $@ ]; then \
	    msgmerge --update --no-fuzzy-matching $@ $(APP_MENU_POT); \
	else \
	    msginit --input=$(APP_MENU_POT) --output=$@ --locale=$* --no-translator; \
	fi

mo-app-menu: $(APP_MENU_MO)

$(LOCALEDIR)/%/LC_MESSAGES/$(APP_MENU_DOMAIN).mo: app-menu/%.po
	@mkdir -p $(dir $@)
	msgfmt --output=$@ $<

# --- Combined targets ---
pot: pot-wizard pot-settings pot-app-menu
po: po-wizard po-settings po-app-menu
mo: mo-wizard mo-settings mo-app-menu

clean:
	rm -f $(WIZARD_POT) $(SETTINGS_POT) $(APP_MENU_POT)
	rm -f $(WIZARD_MO) $(SETTINGS_MO) $(APP_MENU_MO)

all: pot po mo
