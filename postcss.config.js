module.exports = {
  plugins: {
    // Load the Tailwind PostCSS plugin, not the tailwindcss package itself
    '@tailwindcss/postcss': {},
    // Then Autoprefixer
    autoprefixer: {},
  }
};
