#PREFIX is environment variable, but if it is not set, then set default value
ifeq ($(PREFIX),)
	PREFIX := $(DESTDIR)$(HOME)/.local
endif

BINDIR = $(PREFIX)/bin
files := $(wildcard *.sh)

install:
	install -d $(BINDIR)
	install -m 755 $(files) $(BINDIR)

uninstall:
	for file in $(files); do \
		rm $(BINDIR)/"$$file" || exit 1; \
	done
