module.exports = {
  darkMode: 'class',
  content: [
    './templates/**/*.html',
    './dashboard/templates/**/*.html',
    './stakeholders/templates/**/*.html',
    './tasks/templates/**/*.html',
    './legal/templates/**/*.html',
    './assets/templates/**/*.html',
    './cashflow/templates/**/*.html',
    './notes/templates/**/*.html',
    './notes/templatetags/**/*.py',
    './healthcare/templates/**/*.html',
    './email_links/templates/**/*.html',
    './assistant/templates/**/*.html',
    './documents/templates/**/*.html',
    './documents/templatetags/**/*.py',
    './static/js/**/*.js',
    './config/forms.py',
  ],
  theme: {
    extend: {
      colors: {
        sidebar: { DEFAULT: '#1e293b', hover: '#334155', active: '#0f172a' }
      }
    }
  },
}
