import Code_Smells_Detection.Detector.DPy.Utils as Utils
import Code_Smells_Detection.Detector.DPy.Code_Smells_Counter as Code_Smells_Counter
import Code_Smells_Detection.Detector.Utils.Cleaner as Cleaner
import Code_Smells_Detection.Detector.Utils.Saver as Saver
import Code_Smells_Detection.Detector.Detector as Detector


def run(input_path: str, table_path_to_save, state: Saver.StateImplementation, issue_key: str):

    Detector.run_detection(Utils.get_detect_command(input_folder=input_path))

    code_smells_results = Code_Smells_Counter.count_code_smells()

    Saver.save(
        table_path=table_path_to_save,
        program_language=Saver.ProgramLanguage.PYTHON,
        state=state,
        issue_key=issue_key,
        code_smell_results=code_smells_results)

    Cleaner.delete_temp_directory(
        path=Utils.get_detection_output_path(),
        temp_name=Utils.output_temp_directory)






