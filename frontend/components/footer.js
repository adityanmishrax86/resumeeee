// components/footer.js – simple footer with branding

export function initFooter() {
  const footer = document.createElement('footer');
  footer.style.textAlign = 'center';
  footer.style.padding = '1rem';
  footer.style.fontSize = '0.85rem';
  footer.style.color = 'rgba(255,255,255,0.6)';
  footer.textContent = '© 2026 AI Job Copilot – Powered by Antigravity';
  return footer;
}
