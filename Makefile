PREFIX  ?= /usr
DESTDIR ?=

PYTHON_DIST := $(DESTDIR)$(PREFIX)/lib/python3/dist-packages

.PHONY: install uninstall

install:
	# Python package
	install -d $(PYTHON_DIST)/repoman
	cp -r src/repoman/. $(PYTHON_DIST)/repoman/
	find $(PYTHON_DIST)/repoman -name '__pycache__' -exec rm -rf {} + 2>/dev/null; true

	# Entry point
	install -d $(DESTDIR)$(PREFIX)/bin
	install -m 755 bin/repoman $(DESTDIR)$(PREFIX)/bin/repoman

	# Polkit helper
	install -d $(DESTDIR)$(PREFIX)/lib/repoman
	install -m 755 polkit-helper $(DESTDIR)$(PREFIX)/lib/repoman/polkit-helper

	# Desktop integration
	install -d $(DESTDIR)$(PREFIX)/share/applications
	install -m 644 data/net.tecktron.repoman.desktop \
		$(DESTDIR)$(PREFIX)/share/applications/

	install -d $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps
	install -m 644 data/icons/hicolor/scalable/apps/net.tecktron.repoman.svg \
		$(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/
	for size in 16x16 22x22 24x24 32x32 48x48 64x64 128x128 256x256; do \
		install -d $(DESTDIR)$(PREFIX)/share/icons/hicolor/$$size/apps; \
		install -m 644 data/icons/hicolor/$$size/apps/net.tecktron.repoman.png \
			$(DESTDIR)$(PREFIX)/share/icons/hicolor/$$size/apps/; \
	done

	# GSettings schema
	install -d $(DESTDIR)$(PREFIX)/share/glib-2.0/schemas
	install -m 644 data/net.tecktron.repoman.gschema.xml \
		$(DESTDIR)$(PREFIX)/share/glib-2.0/schemas/

	# Polkit policy
	install -d $(DESTDIR)$(PREFIX)/share/polkit-1/actions
	install -m 644 data/net.tecktron.repoman.policy \
		$(DESTDIR)$(PREFIX)/share/polkit-1/actions/

	# Suite-agnostic config
	install -d $(DESTDIR)$(PREFIX)/share/repoman
	install -m 644 data/suite-agnostic.conf \
		$(DESTDIR)$(PREFIX)/share/repoman/suite-agnostic.conf

	# AppStream metadata
	install -d $(DESTDIR)$(PREFIX)/share/metainfo
	install -m 644 data/net.tecktron.repoman.metainfo.xml \
		$(DESTDIR)$(PREFIX)/share/metainfo/

	# Post-install hooks (skipped when DESTDIR is set — package build handles these)
ifeq ($(DESTDIR),)
	glib-compile-schemas $(PREFIX)/share/glib-2.0/schemas/
	gtk-update-icon-cache -f -t $(PREFIX)/share/icons/hicolor
	systemctl reload polkit 2>/dev/null || true
endif

uninstall:
	rm -rf $(DESTDIR)$(PREFIX)/lib/python3/dist-packages/repoman/
	rm -f  $(DESTDIR)$(PREFIX)/bin/repoman
	rm -f  $(DESTDIR)$(PREFIX)/lib/repoman/polkit-helper
	rmdir --ignore-fail-on-non-empty $(DESTDIR)$(PREFIX)/lib/repoman/ 2>/dev/null; true
	rm -f  $(DESTDIR)$(PREFIX)/share/applications/net.tecktron.repoman.desktop
	rm -f  $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps/net.tecktron.repoman.svg
	for size in 16x16 22x22 24x24 32x32 48x48 64x64 128x128 256x256; do \
		rm -f $(DESTDIR)$(PREFIX)/share/icons/hicolor/$$size/apps/net.tecktron.repoman.png; \
		rmdir --ignore-fail-on-non-empty $(DESTDIR)$(PREFIX)/share/icons/hicolor/$$size/apps/ 2>/dev/null; true; \
	done
	rm -f  $(DESTDIR)$(PREFIX)/share/glib-2.0/schemas/net.tecktron.repoman.gschema.xml
	rm -f  $(DESTDIR)$(PREFIX)/share/polkit-1/actions/net.tecktron.repoman.policy
	rm -f  $(DESTDIR)$(PREFIX)/share/repoman/suite-agnostic.conf
	rmdir --ignore-fail-on-non-empty $(DESTDIR)$(PREFIX)/share/repoman/ 2>/dev/null; true
	rm -f  $(DESTDIR)$(PREFIX)/share/metainfo/net.tecktron.repoman.metainfo.xml
ifeq ($(DESTDIR),)
	glib-compile-schemas $(PREFIX)/share/glib-2.0/schemas/
	gtk-update-icon-cache -f -t $(PREFIX)/share/icons/hicolor
endif
