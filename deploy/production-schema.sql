-- Review and run manually against the leda production database only.
-- This migration is based on the currently deployed testing schema.
USE `chbzg`;

CREATE TABLE IF NOT EXISTS `fa_face_service_template` (
  `template_id` varchar(64) NOT NULL,
  `subject_type` varchar(32) NOT NULL,
  `subject_id` varchar(64) NOT NULL,
  `embedding_blob` longblob NOT NULL,
  `embedding_dimension` int(10) unsigned NOT NULL,
  `bbox_json` text NOT NULL,
  `template_version` int(10) unsigned NOT NULL,
  `status` varchar(16) NOT NULL,
  `source_type` varchar(32) NOT NULL,
  `source_image_hash` varchar(128) DEFAULT NULL,
  `created_at` varchar(40) NOT NULL,
  `activated_at` varchar(40) DEFAULT NULL,
  `revoked_at` varchar(40) DEFAULT NULL,
  PRIMARY KEY (`template_id`),
  KEY `idx_face_service_template_subject` (`subject_type`,`subject_id`,`template_version`),
  KEY `idx_face_service_template_active` (`subject_type`,`subject_id`,`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `fa_face_service_session` (
  `session_id` varchar(64) NOT NULL,
  `request_id` varchar(128) DEFAULT NULL,
  `subject_type` varchar(32) NOT NULL,
  `subject_id` varchar(64) NOT NULL,
  `admin_id` varchar(64) DEFAULT NULL,
  `scene` varchar(64) NOT NULL,
  `business_event_id` varchar(128) NOT NULL,
  `record_id` varchar(128) DEFAULT NULL,
  `action` varchar(64) DEFAULT NULL,
  `template_id` varchar(64) NOT NULL,
  `template_version` int(10) unsigned NOT NULL,
  `expected_actions_json` text NOT NULL,
  `upload_token` varchar(128) NOT NULL,
  `upload_token_hash` char(64) NOT NULL,
  `status` varchar(16) NOT NULL,
  `result_code` varchar(64) NOT NULL,
  `issued_at` varchar(40) NOT NULL,
  `expires_at` varchar(40) NOT NULL,
  `verifying_started_at` varchar(40) DEFAULT NULL,
  `verified_at` varchar(40) DEFAULT NULL,
  `proof_id` varchar(64) DEFAULT NULL,
  `action_results_json` longtext,
  PRIMARY KEY (`session_id`),
  UNIQUE KEY `uniq_face_service_session_request` (`request_id`),
  KEY `idx_face_service_session_event` (`business_event_id`,`scene`,`subject_type`,`subject_id`),
  KEY `idx_face_service_session_status` (`status`,`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `fa_face_service_proof` (
  `proof_id` varchar(64) NOT NULL,
  `session_id` varchar(64) NOT NULL,
  `business_event_id` varchar(128) NOT NULL,
  `subject_type` varchar(32) NOT NULL,
  `subject_id` varchar(64) NOT NULL,
  `admin_id` varchar(64) DEFAULT NULL,
  `scene` varchar(64) NOT NULL,
  `record_id` varchar(128) DEFAULT NULL,
  `action` varchar(64) DEFAULT NULL,
  `template_id` varchar(64) NOT NULL,
  `template_version` int(10) unsigned NOT NULL,
  `status` varchar(16) NOT NULL,
  `result_code` varchar(64) NOT NULL,
  `issued_at` varchar(40) NOT NULL,
  `expires_at` varchar(40) NOT NULL,
  `finalized_at` varchar(40) DEFAULT NULL,
  PRIMARY KEY (`proof_id`),
  UNIQUE KEY `uniq_face_service_proof_session` (`session_id`),
  KEY `idx_face_service_proof_event` (`business_event_id`,`scene`,`subject_type`,`subject_id`),
  KEY `idx_face_service_proof_status` (`status`,`expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @face_verify_enabled_exists = (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = 'chbzg'
    AND TABLE_NAME = 'fa_doctor'
    AND COLUMN_NAME = 'face_verify_enabled'
);
SET @face_verify_enabled_ddl = IF(
  @face_verify_enabled_exists = 0,
  'ALTER TABLE `fa_doctor` ADD COLUMN `face_verify_enabled` tinyint(1) NOT NULL DEFAULT 1 COMMENT ''医生刷脸：0关闭，1开启''',
  'SELECT ''fa_doctor.face_verify_enabled already exists'' AS migration_status'
);
PREPARE face_verify_enabled_statement FROM @face_verify_enabled_ddl;
EXECUTE face_verify_enabled_statement;
DEALLOCATE PREPARE face_verify_enabled_statement;

SELECT TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'chbzg'
  AND TABLE_NAME IN (
    'fa_face_service_template',
    'fa_face_service_session',
    'fa_face_service_proof'
  )
ORDER BY TABLE_NAME;

SELECT COLUMN_NAME, COLUMN_TYPE, COLUMN_DEFAULT, COLUMN_COMMENT
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'chbzg'
  AND TABLE_NAME = 'fa_doctor'
  AND COLUMN_NAME = 'face_verify_enabled';
