-- SPDX-License-Identifier: EUPL-1.2
CREATE TABLE IF NOT EXISTS daily_engagement (
  day TEXT NOT NULL,
  path TEXT NOT NULL,
  views INTEGER NOT NULL DEFAULT 0,
  active_seconds INTEGER NOT NULL DEFAULT 0,
  downloads INTEGER NOT NULL DEFAULT 0,
  scrolled_views INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day,path)
);
