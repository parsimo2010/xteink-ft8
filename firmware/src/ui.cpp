#include "ui.h"
#include "font5x7.h"

void Ui::pixel(uint16_t x, uint16_t y, bool black) {
  if (x >= _w || y >= _h || !_fb) return;
  uint16_t byteIndex = y * _rowBytes + (x >> 3);
  uint8_t bit = 7 - (x & 7);
  if (black) {
    _fb[byteIndex] &= ~(1u << bit);
  } else {
    _fb[byteIndex] |= (1u << bit);
  }
}

bool Ui::pixelRead(uint16_t x, uint16_t y) const {
  if (x >= _w || y >= _h || !_fb) return false;
  uint16_t byteIndex = y * _rowBytes + (x >> 3);
  uint8_t bit = 7 - (x & 7);
  return (_fb[byteIndex] & (1u << bit)) != 0;
}

void Ui::clear() {
  if (!_fb) return;
  for (uint32_t i = 0; i < (uint32_t)_w * _h / 8; i++) _fb[i] = 0xFF;
}

void Ui::fill(uint16_t x, uint16_t y, uint16_t w, uint16_t h, bool black) {
  for (uint16_t yy = y; yy < y + h; yy++)
    for (uint16_t xx = x; xx < x + w; xx++) pixel(xx, yy, black);
}

void Ui::invert(uint16_t x, uint16_t y, uint16_t w, uint16_t h) {
  for (uint16_t yy = y; yy < y + h; yy++)
    for (uint16_t xx = x; xx < x + w; xx++) pixel(xx, yy, !pixelRead(xx, yy));
}

void Ui::hline(uint16_t x, uint16_t y, uint16_t w, bool black) {
  for (uint16_t i = 0; i < w; i++) pixel(x + i, y, black);
}

void Ui::vline(uint16_t x, uint16_t y, uint16_t h, bool black) {
  for (uint16_t i = 0; i < h; i++) pixel(x, y + i, black);
}

void Ui::rect(uint16_t x, uint16_t y, uint16_t w, uint16_t h, bool black) {
  hline(x, y, w, black);
  hline(x, y + h - 1, w, black);
  vline(x, y, h, black);
  vline(x + w - 1, y, h, black);
}

uint16_t Ui::text(uint16_t x, uint16_t y, const char* s, bool black) {
  uint16_t cx = x;
  while (s && *s) {
    unsigned char c = (unsigned char)*s++;
    if (c < 0x20 || c > 0x7E) c = ' ';
    const uint8_t* g = &font5x7[(c - 0x20) * FONT_CHAR_W];
    for (uint8_t col = 0; col < FONT_CHAR_W; col++) {
      for (uint8_t row = 0; row < FONT_CHAR_H; row++) {
        if (g[col] & (1u << row)) pixel(cx + col, y + row, black);
      }
    }
    cx += FONT_CHAR_W + FONT_X_OFFSET;
  }
  return cx - x;
}

uint16_t Ui::textWidth(const char* s) const {
  uint16_t n = 0;
  while (s && *s++) n++;
  return n > 0 ? n * (FONT_CHAR_W + FONT_X_OFFSET) : 0;
}