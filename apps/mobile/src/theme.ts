/** Nhạc visual language: dark, nostalgic, warm accent. */
export const theme = {
  colors: {
    bg: '#0b0b0f',
    surface: '#16161d',
    surfaceAlt: '#1f1f29',
    text: '#f5f3ef',
    textMuted: '#9a97a3',
    accent: '#e0a458', // warm amber — golden-hour nostalgia
    accentAlt: '#c96f6f',
    border: '#2a2a35',
  },
  radius: { sm: 8, md: 14, lg: 22 },
  spacing: (n: number) => n * 8,
} as const;
