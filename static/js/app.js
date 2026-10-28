document.addEventListener('DOMContentLoaded', () => {
  // Prevent duplicate form submission
  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', () => {
      const button = form.querySelector('button[type="submit"]');
      if (button) {
        button.disabled = true;
        button.dataset.originalText = button.textContent;
        button.textContent = 'Please wait…';
      }
    });
  });

  // Highlight active link in sidebar navigation
  const currentPath = window.location.pathname;
  const sidebarLinks = Array.from(document.querySelectorAll('.sidebar-nav a'));
  if (sidebarLinks.length > 0) {
    // Sort links by href length descending so specific paths take precedence
    sidebarLinks.sort((a, b) => (b.getAttribute('href') || '').length - (a.getAttribute('href') || '').length);

    let matched = false;
    for (const link of sidebarLinks) {
      const href = link.getAttribute('href');
      if (!href) continue;
      if (currentPath === href || (href !== '/' && href !== '/dashboard/' && currentPath.startsWith(href))) {
        link.classList.add('active');
        // Scroll active item smoothly into view within fixed sidebar if overflowing
        try {
          link.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        } catch (e) {}
        matched = true;
        break;
      }
    }
    if (!matched) {
      const defaultActive = document.querySelector('.sidebar-nav a[href="' + currentPath + '"]');
      if (defaultActive) defaultActive.classList.add('active');
    }
  }

  // Mobile fixed sidebar drawer toggle
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const sidebarCollapseToggle = document.getElementById('sidebar-collapse-toggle');
  const sidebarClose = document.getElementById('sidebar-close');
  const adminSidebar = document.getElementById('admin-sidebar');
  const sidebarBackdrop = document.getElementById('sidebar-backdrop');

  function setSidebarCollapsed(collapsed) {
    const preStyle = document.getElementById('pre-sidebar-style');
    if (preStyle) preStyle.remove();
    document.documentElement.classList.toggle('sidebar-collapsed', collapsed);
    document.body.classList.toggle('sidebar-collapsed', collapsed);
    try {
      localStorage.setItem('admin-sidebar-collapsed', collapsed ? 'true' : 'false');
    } catch (e) {}
    if (sidebarCollapseToggle) {
      sidebarCollapseToggle.setAttribute('aria-expanded', String(!collapsed));
      sidebarCollapseToggle.setAttribute('aria-label', collapsed ? 'Open sidebar navigation' : 'Hide sidebar navigation');
      sidebarCollapseToggle.title = collapsed ? 'Open sidebar navigation' : 'Hide sidebar navigation';
    }
  }

  // Restore saved collapse state on desktop
  try {
    if (localStorage.getItem('admin-sidebar-collapsed') === 'true' && window.innerWidth >= 992) {
      document.documentElement.classList.add('sidebar-collapsed');
      document.body.classList.add('sidebar-collapsed');
      if (sidebarCollapseToggle) {
        sidebarCollapseToggle.setAttribute('aria-expanded', 'false');
        sidebarCollapseToggle.setAttribute('aria-label', 'Open sidebar navigation');
        sidebarCollapseToggle.title = 'Open sidebar navigation';
      }
    }
  } catch (e) {}

  function openSidebar() {
    if (adminSidebar) adminSidebar.classList.add('show');
    if (sidebarBackdrop) sidebarBackdrop.classList.add('show');
    document.body.classList.add('sidebar-open');
    if (sidebarToggle) sidebarToggle.setAttribute('aria-expanded', 'true');
  }

  function closeSidebar() {
    if (adminSidebar) adminSidebar.classList.remove('show');
    if (sidebarBackdrop) sidebarBackdrop.classList.remove('show');
    document.body.classList.remove('sidebar-open');
    if (sidebarToggle) sidebarToggle.setAttribute('aria-expanded', 'false');
  }

  if (sidebarToggle) sidebarToggle.addEventListener('click', openSidebar);
  if (sidebarCollapseToggle) {
    sidebarCollapseToggle.addEventListener('click', () => {
      document.documentElement.classList.add('sidebar-interactive');
      document.body.classList.add('sidebar-interactive');
      const isCurrentlyCollapsed = document.documentElement.classList.contains('sidebar-collapsed') || document.body.classList.contains('sidebar-collapsed');
      setSidebarCollapsed(!isCurrentlyCollapsed);
    });
  }
  if (sidebarClose) sidebarClose.addEventListener('click', closeSidebar);
  if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', closeSidebar);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && adminSidebar && adminSidebar.classList.contains('show')) {
      closeSidebar();
    }
  });
});
