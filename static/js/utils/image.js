// 图片懒加载工具
function lazyLoadImages() {
  const imgs = document.querySelectorAll('.lazy-img[data-src]');
  if (!imgs.length) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const img = entry.target;
        img.src = img.dataset.src;
        img.removeAttribute('data-src');
        img.onerror = function() {
          if (this.dataset.srcFallback) {
            this.src = this.dataset.srcFallback;
            this.removeAttribute('data-src-fallback');
          } else {
            this.style.display = 'none';
            if (this.nextElementSibling) {
              this.nextElementSibling.style.display = 'flex';
            }
          }
        };
        observer.unobserve(img);
      }
    });
  });

  imgs.forEach(img => observer.observe(img));
}