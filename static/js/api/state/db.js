// ==================== State 查询工具 ====================
// 事件系统已迁移到 namespace.js

State.db = {
  find: function(table, id) {
    if (table === 'authors') return State.authors.get(id);
    if (table === 'videos') return State.videos.get(id);
    if (table === 'tasks') return State.tasks.get(id);
    if (table === 'catalog') return State.catalog.get(id);
    return null;
  },

  all: function(table) {
    if (table === 'authors') return State.authors.all();
    if (table === 'videos') return State.videos.all();
    if (table === 'tasks') return State.tasks.all();
    if (table === 'catalog') return State.catalog.all();
    return [];
  },

  where: function(table, filter) {
    return State.db.all(table).filter(filter);
  }
};
