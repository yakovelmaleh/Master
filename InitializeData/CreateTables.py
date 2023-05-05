"""
=================================================
create table which is saving all the changes
=================================================
"""
all_changes_os = """
    CREATE TABLE `all_changes_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `author` varchar(200) DEFAULT NULL,
      `created` datetime DEFAULT NULL,
      `from_string` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `to_string` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `field` varchar(200) DEFAULT NULL,
      `if_change_first_hour` int(11) DEFAULT NULL,
      `different_time_from_creat` float DEFAULT NULL,
      `is_first_setup` int(11) DEFAULT NULL,
      `chronological_number` int(11) NOT NULL,
      PRIMARY KEY (`issue_key`,`chronological_number`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving all the changes in description field
======================================================================
"""
changes_description_os = """
    CREATE TABLE `changes_description_os` (
      `issue_key` char(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
      `project_key` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
      `author` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
      `created` datetime DEFAULT NULL,
      `from_string` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci,
      `to_string` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci,
      `if_change_first_hour` int(11) DEFAULT NULL,
      `different_time_from_creat` float DEFAULT NULL,
      `is_first_setup` int(11) DEFAULT NULL,
      `is_diff_more_than_ten` int(11) DEFAULT NULL,
      `chronological_number` int(11) NOT NULL,
      # different from from str to to srt (the next after him)
      `ratio_different_char_next` float DEFAULT NULL,
      `ratio_different_word_next` float DEFAULT NULL,
      `num_different_char_minus_next` INT DEFAULT NULL,
      `num_different_char_plus_next` INT DEFAULT NULL,
      `num_different_char_all_next` INT DEFAULT NULL,
      `num_different_word_minus_next` INT DEFAULT NULL,
      `num_different_word_plus_next` INT DEFAULT NULL,
      `num_different_word_all_next` INT DEFAULT NULL,
      # different from from str to current(last) value (the final value)
      `ratio_different_char_last` float DEFAULT NULL,
      `ratio_different_word_last` float DEFAULT NULL,
      `num_different_char_minus_last` INT DEFAULT NULL,
      `num_different_char_plus_last` INT DEFAULT NULL,
      `num_different_char_all_last` INT DEFAULT NULL,
      `num_different_word_minus_last` INT DEFAULT NULL,
      `num_different_word_plus_last` INT DEFAULT NULL,
      `num_different_word_all_last` INT DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`chronological_number`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """

"""
======================================================================
create table which is saving all the changes in sprint 
======================================================================
"""
changes_sprint_os = """
    CREATE TABLE `changes_sprint_os` (
      `issue_key` char(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
      `project_key` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
      `author` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
      `created` datetime DEFAULT NULL,
      `from_string` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `to_string` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `if_change_first_hour` int(11) DEFAULT NULL,
      `different_time_from_creat` float DEFAULT NULL,
      `is_first_setup` int(11) DEFAULT NULL,
      `chronological_number` int(11) NOT NULL,
      PRIMARY KEY (`issue_key`,`chronological_number`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """

"""
======================================================================
create table which is saving all the changes in story point field 
======================================================================
"""
changes_story_points_os = """
    CREATE TABLE `changes_story_points_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `author` varchar(200) DEFAULT NULL,
      `created` datetime DEFAULT NULL,
      `from_string` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `to_string` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `if_change_first_hour` int(11) DEFAULT NULL,
      `different_time_from_creat` float DEFAULT NULL,
      `is_first_setup` int(11) DEFAULT NULL,
      `chronological_number` int(11) NOT NULL,
      PRIMARY KEY (`issue_key`,`chronological_number`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving all the changes in summary field 
======================================================================
"""
changes_summary_os = """
    CREATE TABLE `changes_summary_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `author` varchar(200) DEFAULT NULL,
      `created` datetime DEFAULT NULL,
      `from_string` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `to_string` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `if_change_first_hour` int(11) DEFAULT NULL,
      `different_time_from_creat` float DEFAULT NULL,
      `is_first_setup` int(11) DEFAULT NULL,
      `is_diff_more_than_ten` int(11) DEFAULT NULL,
      `chronological_number` int(11) NOT NULL,
      # different from from str to to srt (the next after him)
      `ratio_different_char_next` float DEFAULT NULL,
      `ratio_different_word_next` float DEFAULT NULL,
      `num_different_char_minus_next` INT DEFAULT NULL,
      `num_different_char_plus_next` INT DEFAULT NULL,
      `num_different_char_all_next` INT DEFAULT NULL,
      `num_different_word_minus_next` INT DEFAULT NULL,
      `num_different_word_plus_next` INT DEFAULT NULL,
      `num_different_word_all_next` INT DEFAULT NULL,
      # different from from str to current(last) value (the final value)
      `ratio_different_char_last` float DEFAULT NULL,
      `ratio_different_word_last` float DEFAULT NULL,
      `num_different_char_minus_last` INT DEFAULT NULL,
      `num_different_char_plus_last` INT DEFAULT NULL,
      `num_different_char_all_last` INT DEFAULT NULL,
      `num_different_word_minus_last` INT DEFAULT NULL,
      `num_different_word_plus_last` INT DEFAULT NULL,
      `num_different_word_all_last` INT DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`chronological_number`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving all the changes in criteria field 
======================================================================
"""
changes_criteria_os = """
    CREATE TABLE `changes_criteria_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `author` varchar(200) DEFAULT NULL,
      `created` datetime DEFAULT NULL,
      `from_string` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `to_string` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `if_change_first_hour` int(11) DEFAULT NULL,
      `different_time_from_creat` float DEFAULT NULL,
      `is_first_setup` int(11) DEFAULT NULL,
      `is_diff_more_than_ten` int(11) DEFAULT NULL,
      `chronological_number` int(11) NOT NULL,
      # different from from str to to srt (the next after him)
      `ratio_different_char_next` float DEFAULT NULL,
      `ratio_different_word_next` float DEFAULT NULL,
      `num_different_char_minus_next` INT DEFAULT NULL,
      `num_different_char_plus_next` INT DEFAULT NULL,
      `num_different_char_all_next` INT DEFAULT NULL,
      `num_different_word_minus_next` INT DEFAULT NULL,
      `num_different_word_plus_next` INT DEFAULT NULL,
      `num_different_word_all_next` INT DEFAULT NULL,
      # different from from str to current(last) value (the final value)
      `ratio_different_char_last` float DEFAULT NULL,
      `ratio_different_word_last` float DEFAULT NULL,
      `num_different_char_minus_last` INT DEFAULT NULL,
      `num_different_char_plus_last` INT DEFAULT NULL,
      `num_different_char_all_last` INT DEFAULT NULL,
      `num_different_word_minus_last` INT DEFAULT NULL,
      `num_different_word_plus_last` INT DEFAULT NULL,
      `num_different_word_all_last` INT DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`chronological_number`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving all the comments 
======================================================================
"""
comments_os = """
    CREATE TABLE `comments_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `author` varchar(200) DEFAULT NULL,
      `id` int(20) NOT NULL,
      `created` datetime DEFAULT NULL,
      `body` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `chronological_number` int(11) DEFAULT NULL,
      `clean_comment` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      PRIMARY KEY (`issue_key`,`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving all the commits info 
======================================================================
"""
commits_info_os = """
    CREATE TABLE `commits_info_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `author` varchar(200) DEFAULT NULL,
      `insertions` int(11) DEFAULT NULL,
      `code_deletions` int(11) DEFAULT NULL,
      `code_lines` int(11) DEFAULT NULL,
      `files` int(11) DEFAULT NULL,
      `message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `commit` varchar(500) NOT NULL,
      `chronological_number` int(11) DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`commit`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving all the components info 
======================================================================
"""
components_os = """
    CREATE TABLE `components_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `component` varchar(200) NOT NULL,
      `chronological_order` int(11) DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`component`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving all the fix_versions info 
======================================================================
"""
fix_versions_os = """
    CREATE TABLE `fix_versions_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `fix_version` varchar(100) NOT NULL,
      `chronological_number` int(11) DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`fix_version`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving all the issue links 
======================================================================
"""
issue_links_os = """
    CREATE TABLE `issue_links_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `issue_link` varchar(100) NOT NULL,
      `issue_link_name_relation` varchar(200) DEFAULT NULL,
      `chronological_number` int(11) DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`issue_link`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving all the labels info 
======================================================================
"""
labels_os = """
    CREATE TABLE `labels_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `label` varchar(100) NOT NULL,
      `chronological_number` int(11) DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`label`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving all the attachment files info 
======================================================================
"""
attachment_os = """
    CREATE TABLE `attachment_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `attachment_id` INT NOT NULL,
      `file_type` varchar(100) NOT NULL,
      `creator` varchar(100) NOT NULL,
      `created` datetime NOT NULL,
      PRIMARY KEY (`attachment_id`,`issue_key`,`project_key`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create the main table with all the nessecary data, and extra
======================================================================
"""
main_table_os = """
    CREATE TABLE `main_table_os` (
      `issue_key` char(50) NOT NULL,
      `issue_id` int(20) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `created` datetime NOT NULL,
      `creator` varchar(100) NOT NULL,
      `reporter` varchar(100) NOT NULL,
      `assignee` varchar(200) DEFAULT NULL,
      `date_of_first_response` datetime DEFAULT NULL,
      `epic_link` varchar(100) DEFAULT NULL,
      `issue_type` varchar(45) NOT NULL,
      `last_updated` datetime DEFAULT NULL,
      `priority` varchar(100) DEFAULT NULL,
      `prograss` float DEFAULT NULL,
      `prograss_total` float DEFAULT NULL,
      `resolution` varchar(100) DEFAULT NULL,
      `resolution_date` datetime DEFAULT NULL,
      `status_name` varchar(100) DEFAULT NULL,
      `status_description` varchar(200) DEFAULT NULL,
      `time_estimate` float DEFAULT NULL,
      `time_origion_estimate` float DEFAULT NULL,
      `time_spent` float DEFAULT NULL,
      `attachment` INT DEFAULT NULL,
      `is_attachment` INT DEFAULT NULL,
      `pull_request_url` varchar(500) DEFAULT NULL,
      `images` INT DEFAULT NULL,
      `is_images` INT DEFAULT NULL,
      `team` varchar(100) DEFAULT NULL,  
      `story_point` float DEFAULT NULL,
      `summary` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `description` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `acceptance_criteria` mediumtext CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci,
      `num_all_changes` int(11) DEFAULT NULL,
      `num_bugs_issue_link` int(11) DEFAULT NULL,
      `num_changes_summary` int(11) DEFAULT NULL,
      `num_changes_description` int(11) DEFAULT NULL,
      `num_changes_acceptance_criteria` int(11) DEFAULT NULL,
      `num_changes_story_point` int(11) DEFAULT NULL,
      `num_comments` int(11) DEFAULT NULL,
      `num_issue_links` int(11) DEFAULT NULL,
      `num_of_commits` int(11) DEFAULT NULL,
      `num_sprints` int(11) DEFAULT NULL,
      `num_sub_tasks` int(11) DEFAULT NULL,
      `num_watchers` int(11) DEFAULT NULL,
      `num_worklog` int(11) DEFAULT NULL,
      `num_versions` int(11) DEFAULT NULL,
      `num_fix_versions` int(11) DEFAULT NULL,
      `num_labels` int(11) DEFAULT NULL,
      `num_components` int(11) DEFAULT NULL,
      `original_summary` mediumtext,
      `num_changes_summary_new` int(11) DEFAULT NULL,
      `original_description` mediumtext,
      `num_changes_description_new` int(11) DEFAULT NULL,
      `original_acceptance_criteria` mediumtext,
      `num_changes_acceptance_criteria_new` int(11) DEFAULT NULL,
      `original_story_points` float DEFAULT NULL,
      `num_changes_story_points_new` int(11) DEFAULT NULL,
      `has_change_summary` int(11) DEFAULT NULL,
      `has_change_description` int(11) DEFAULT NULL,
      `has_change_acceptance_criteria` int(11) DEFAULT NULL,
      `has_change_story_point` int(11) DEFAULT NULL,
      `num_changes_sprint` int(11) DEFAULT NULL,
      `original_summary_description_acceptance` mediumtext,
      `num_changes_summary_description_acceptance` int(11) DEFAULT NULL,
      `has_changes_summary_description_acceptance` int(11) DEFAULT NULL,
      `has_change_summary_description_acceptance_after_sprint` int(11) DEFAULT NULL,
      `has_change_summary_after_sprint` int(11) DEFAULT NULL,
      `has_change_description_after_sprint` int(11) DEFAULT NULL,
      `has_change_acceptance_criteria_after_sprint` int(11) DEFAULT NULL,
      # add feature time_add_to_sprint:
      `time_add_to_sprint` DATETIME DEFAULT NULL,
      # add another features open source:
      `original_summary_sprint` MEDIUMTEXT DEFAULT NULL,
      `num_changes_summary_new_sprint` INT(11) DEFAULT NULL,
      `original_description_sprint` MEDIUMTEXT DEFAULT NULL,
      `num_changes_description_new_sprint` INT(11) DEFAULT NULL,
      `original_acceptance_criteria_sprint` MEDIUMTEXT DEFAULT NULL,
      `num_changes_acceptance_criteria_new_sprint` INT(11) DEFAULT NULL,
      `original_story_points_sprint` FLOAT DEFAULT NULL,
      `num_changes_story_points_new_sprint` INT(11) DEFAULT NULL,
      `has_change_summary_sprint` INT(11) DEFAULT NULL,
      `has_change_description_sprint` INT(11) DEFAULT NULL,
      `has_change_acceptance_criteria_sprint` INT(11) DEFAULT NULL,
      `has_change_story_point_sprint` INT(11) DEFAULT NULL,
      # add the different word count and word ration between before and after sprint
      `different_words_minus_summary` INT(11) DEFAULT NULL,
      `different_words_plus_summary` INT(11) DEFAULT NULL,
      `different_words_minus_description` INT(11) DEFAULT NULL,
      `different_words_plus_description` INT(11) DEFAULT NULL,
      `different_words_minus_acceptance_criteria` INT(11) DEFAULT NULL,
      `different_words_plus_acceptance_criteria` INT(11) DEFAULT NULL,
      `different_words_ratio_all_summary` FLOAT DEFAULT NULL,
      `different_words_ratio_all_description` FLOAT DEFAULT NULL,
      `different_words_ratio_all_acceptance_criteria` FLOAT DEFAULT NULL,
      `different_words_minus_summary_sprint` INT(11) DEFAULT NULL,
      `different_words_plus_summary_sprint` INT(11) DEFAULT NULL,
      `different_words_minus_description_sprint` INT(11) DEFAULT NULL,
      `different_words_plus_description_sprint` INT(11) DEFAULT NULL,
      `different_words_minus_acceptance_criteria_sprint` INT(11) DEFAULT NULL,
      `different_words_plus_acceptance_criteria_sprint` INT(11) DEFAULT NULL,
      `different_words_ratio_all_summary_sprint` FLOAT DEFAULT NULL,
      `different_words_ratio_all_description_sprint` FLOAT DEFAULT NULL,
      `different_words_ratio_all_acceptance_criteria_sprint` FLOAT DEFAULT NULL,
      `num_comments_before_sprint` INT(11) DEFAULT NULL,
      `num_comments_after_sprint` INT(11) DEFAULT NULL,
      `num_different_words_all_text_sprint_new` int(11) DEFAULT NULL,
      `num_ratio_words_all_text_sprint_new` float DEFAULT NULL,
      `num_changes_text_before_sprint` int(11) DEFAULT NULL,
      `num_changes_story_point_before_sprint` int(11) DEFAULT NULL,
      `time_status_close` datetime DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`issue_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving the bugs info
======================================================================
"""
names_bugs_issue_links_os = """
    CREATE TABLE `names_bugs_issue_links_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `bug_issue_link` varchar(100) NOT NULL,
      `chronological_number` int(11) DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`bug_issue_link`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving the sab tasks info
======================================================================
"""
sab_task_names_os = """
     CREATE TABLE `sab_task_names_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `sub_task_name` varchar(200) NOT NULL,
      `chronological_number` int(11) DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`sub_task_name`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving the sprints info
======================================================================
"""
sprints_os = """
    CREATE TABLE `sprints_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `sprint_name` varchar(300) NOT NULL,
      `start_date` datetime DEFAULT NULL,
      `end_date` datetime DEFAULT NULL,
      `is_over` int(11) DEFAULT NULL,
      `chronological_number` int(11) DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`sprint_name`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """

"""
======================================================================
create table which is saving the versions info
======================================================================
"""
versions_os = """
    CREATE TABLE `versions_os` (
      `issue_key` char(50) NOT NULL,
      `project_key` varchar(45) NOT NULL,
      `version` varchar(200) NOT NULL,
      `chronological_number` int(11) DEFAULT NULL,
      PRIMARY KEY (`issue_key`,`version`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """