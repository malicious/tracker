PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "Tasks" (
	task_id INTEGER NOT NULL, 
	"desc" VARCHAR NOT NULL, 
	first_scope VARCHAR(20) NOT NULL, 
	category VARCHAR, 
	created_at DATETIME, 
	resolution VARCHAR, 
	parent_id INTEGER, 
	time_estimate FLOAT, 
	time_actual FLOAT, 
	PRIMARY KEY (task_id), 
	UNIQUE ("desc", created_at), 
	UNIQUE (task_id), 
	FOREIGN KEY(parent_id) REFERENCES "Tasks" (task_id)
);
INSERT INTO "Tasks" VALUES(1,'start with "print the same markdown doc" for imported lines','2020-ww35.5','tasks_v1','2020-08-29 01:20:52','done',NULL,12.0,NULL);
INSERT INTO "Tasks" VALUES(2,'so it can be imported + you can reverse it','2020-ww35.5','tasks_v1','2020-08-29 02:00:00','info',1,NULL,NULL);
INSERT INTO "Tasks" VALUES(3,'so there''s a sustainable way to review old data, without repeating work (by re-reading lines)','2020-ww35.5','tasks_v1','2020-08-30 18:00:01','info',1,NULL,NULL);
INSERT INTO "Tasks" VALUES(4,'it seems like importing redundant tasks might be similar to a database upgrade','2020-ww37.4','tasks_v1','2020-09-10 11:45:45','info',NULL,NULL,NULL);
INSERT INTO "Tasks" VALUES(5,'well. volume is still low, so i''m not gonna worry about it','2020-ww37.4','tasks_v1','2020-09-10 11:45:45','info',4,NULL,NULL);
INSERT INTO "Tasks" VALUES(6,'add support for _quarters_','2020-ww37.4','tasks_v1','2020-09-11 00:13:23','done',NULL,NULL,NULL);
INSERT INTO "Tasks" VALUES(7,'dump parent tasks in HTML detail views','2020-ww37.4','tasks_v1','2020-09-11 00:13:23','done',6,NULL,NULL);
INSERT INTO "Tasks" VALUES(8,'print `(roll => ww37.4)` when a task has moved to a later week','2020-ww37.4','tasks_v1','2020-09-11 00:13:23','done',6,NULL,NULL);
INSERT INTO "Tasks" VALUES(9,'optional, rewrite mdown_to_csv.py','2020-ww37.4','tasks_v1','2020-09-11 00:13:23','dropped',6,NULL,NULL);
INSERT INTO "Tasks" VALUES(10,'make CLI for entering tasks, because that''s _significantly_ easier than editing the database manually','2020-ww37.6','tasks_v1','2020-09-13 04:35:22','done',NULL,NULL,NULL);
INSERT INTO "Tasks" VALUES(11,'can i make a CLI support mdown => json? CSV? how to make it UNIX-y?','2020-ww37.6','tasks_v1','2020-09-13 04:35:22','done',10,NULL,NULL);
INSERT INTO "Tasks" VALUES(12,'did it super manually: scopes and description, plus an update function for today + resolution (things are rarely more complex than that, sub-tasks are probably just a legacy thing?)','2020-ww37.6','tasks_v1','2020-09-13 04:35:22','info',10,NULL,NULL);
INSERT INTO "Tasks" VALUES(13,'for `flask add-task`, swap entry order for description/time scope','2020-ww42.3','tasks_v1','2020-10-14 16:21:21','done',NULL,NULL,NULL);
INSERT INTO "Tasks" VALUES(14,'the `(roll => ww43)` printing works wonky with ww43 => ww43.2, since it''s a weird ordering','2020-ww43.2','tasks_v1','2020-10-20 20:28:47',NULL,NULL,NULL,NULL);
INSERT INTO "Tasks" VALUES(15,'not to mention `2020—Q4`','2020-ww43.2','tasks_v1','2020-10-20 20:28:47','info',14,NULL,NULL);
INSERT INTO "Tasks" VALUES(16,'not gonna fix this without rethinking semantic ordering; this works fine for now','2020-ww43.2','tasks_v1','2020-11-04 02:05:00','info',14,NULL,NULL);
INSERT INTO "Tasks" VALUES(17,'a time_estimate of `0.0` doesn''t show up','2020-ww43.5','tasks_v1','2020-10-23 15:39:08','done',NULL,NULL,NULL);
INSERT INTO "Tasks" VALUES(18,'change "roll" status to take precedent over actual statuses','2020-ww43.7','tasks_v1','2020-10-25 18:31:01','done',NULL,NULL,NULL);
INSERT INTO "Tasks" VALUES(19,'also... add estimates to `flask add-task`, they go a long way towards prioritizing + sorting','2020-ww44.6','tasks_v1','2020-10-31 18:17:46','done',NULL,NULL,NULL);
INSERT INTO "Tasks" VALUES(20,'make task entry loop, so i don''t have to `flask add-task` all the time','2020-ww44.7','tasks_v1','2020-11-01 21:08:53','dropped',NULL,NULL,NULL);
INSERT INTO "Tasks" VALUES(21,'time_actual field doesn''t go well; entry gets truncated, and so does reporting','2020-ww46.6','tasks_v1','2020-11-15 00:22:08',NULL,NULL,NULL,NULL);
INSERT INTO "Tasks" VALUES(22,'maybe it''s time to actually turn it into a fixed-width text field? and just validate that it turns into numbers correctly?','2020-ww46.6','tasks_v1','2020-11-26 01:25:00','info',21,NULL,NULL);
CREATE TABLE IF NOT EXISTS "TaskTimeScopes" (
	task_id INTEGER NOT NULL, 
	time_scope_id VARCHAR NOT NULL, 
	PRIMARY KEY (task_id, time_scope_id), 
	UNIQUE (task_id, time_scope_id), 
	FOREIGN KEY(task_id) REFERENCES "Tasks" (task_id)
);
INSERT INTO "TaskTimeScopes" VALUES(1,'2020-ww35.5');
INSERT INTO "TaskTimeScopes" VALUES(2,'2020-ww35.5');
INSERT INTO "TaskTimeScopes" VALUES(3,'2020-ww35.5');
INSERT INTO "TaskTimeScopes" VALUES(4,'2020-ww37.4');
INSERT INTO "TaskTimeScopes" VALUES(5,'2020-ww37.4');
INSERT INTO "TaskTimeScopes" VALUES(6,'2020-ww37.4');
INSERT INTO "TaskTimeScopes" VALUES(7,'2020-ww37.4');
INSERT INTO "TaskTimeScopes" VALUES(8,'2020-ww37.4');
INSERT INTO "TaskTimeScopes" VALUES(9,'2020-ww37.4');
INSERT INTO "TaskTimeScopes" VALUES(10,'2020-ww37.6');
INSERT INTO "TaskTimeScopes" VALUES(11,'2020-ww37.6');
INSERT INTO "TaskTimeScopes" VALUES(12,'2020-ww37.6');
INSERT INTO "TaskTimeScopes" VALUES(13,'2020-ww42.3');
INSERT INTO "TaskTimeScopes" VALUES(14,'2020-ww43.2');
INSERT INTO "TaskTimeScopes" VALUES(15,'2020-ww43.2');
INSERT INTO "TaskTimeScopes" VALUES(16,'2020-ww43.2');
INSERT INTO "TaskTimeScopes" VALUES(17,'2020-ww43.5');
INSERT INTO "TaskTimeScopes" VALUES(18,'2020-ww43.7');
INSERT INTO "TaskTimeScopes" VALUES(19,'2020-ww44.6');
INSERT INTO "TaskTimeScopes" VALUES(20,'2020-ww44.7');
INSERT INTO "TaskTimeScopes" VALUES(21,'2020-ww46.6');
INSERT INTO "TaskTimeScopes" VALUES(22,'2020-ww46.6');
COMMIT;
