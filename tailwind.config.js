/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.html',
    './app/**/*.jinja2'
  ],
  theme: {
    extend: {
      colors: {
        figurella: '#CC0066'
      }
    }
  },
  plugins: []
}
