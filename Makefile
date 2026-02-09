TAILWIND_VERSION := 3.4.17
TAILWIND_BIN := ./bin/tailwindcss

# Detect OS and architecture
UNAME_S := $(shell uname -s)
UNAME_M := $(shell uname -m)

ifeq ($(UNAME_S),Linux)
  ifeq ($(UNAME_M),x86_64)
    TAILWIND_PLATFORM := linux-x64
  else ifeq ($(UNAME_M),aarch64)
    TAILWIND_PLATFORM := linux-arm64
  endif
else ifeq ($(UNAME_S),Darwin)
  ifeq ($(UNAME_M),x86_64)
    TAILWIND_PLATFORM := macos-x64
  else ifeq ($(UNAME_M),arm64)
    TAILWIND_PLATFORM := macos-arm64
  endif
endif

TAILWIND_URL := https://github.com/tailwindlabs/tailwindcss/releases/download/v$(TAILWIND_VERSION)/tailwindcss-$(TAILWIND_PLATFORM)

.PHONY: tailwind-install tailwind-build tailwind-watch

tailwind-install:
	mkdir -p bin
	curl -sLo $(TAILWIND_BIN) $(TAILWIND_URL)
	chmod +x $(TAILWIND_BIN)
	@echo "Tailwind CSS $(TAILWIND_VERSION) installed to $(TAILWIND_BIN)"

tailwind-build:
	$(TAILWIND_BIN) -i static/css/input.css -o static/css/tailwind.css --minify

tailwind-watch:
	$(TAILWIND_BIN) -i static/css/input.css -o static/css/tailwind.css --watch
