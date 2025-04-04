import xlsxwriter

def create_review_spreadsheet(grading_data: dict, f_path: str, filename: str, exercise_type: str = "ER") -> None:
    """
    Creates a formatted Excel spreadsheet displaying student scores for any exercise type.
    
    Args:
        grading_data (dict): Dictionary containing grading information
        f_path (str): File path of the student submission
        filename (str): Original filename of the submission
        exercise_type (str): Type of exercise (e.g., "ER", "keys"), defaults to "ER"
    """
    # Prepare output filename
    f_name_parts = filename.split(".")
    output_filename = f"{f_name_parts[0]}_Scores.{f_name_parts[-1]}"
    
    # Create workbook and worksheet
    workbook = xlsxwriter.Workbook(output_filename)
    worksheet = workbook.add_worksheet("Scores")
    
    # Define formats
    header_format = workbook.add_format({
        'bold': True,
        'bg_color': '#4F81BD',
        'font_color': 'white',
        'align': 'center',
        'valign': 'vcenter',
        'border': 1
    })
    
    title_format = workbook.add_format({
        'bold': True,
        'font_size': 14,
        'align': 'center',
        'valign': 'vcenter'
    })
    
    cell_format = workbook.add_format({
        'border': 1,
        'align': 'left',
        'valign': 'vcenter'
    })
    
    percent_format = workbook.add_format({
        'border': 1,
        'num_format': '0.00%',
        'align': 'right'
    })
    
    number_format = workbook.add_format({
        'border': 1,
        'num_format': '#,##0.00',
        'align': 'right'
    })
    
    # Set column widths
    worksheet.set_column(0, 0, 25)  # Category column
    worksheet.set_column(1, 1, 15)  # Score column
    
    # Write title with exercise type
    worksheet.merge_range('A1:B1', f'{exercise_type.upper()} Exercise Scores', title_format)
    
    # Write headers
    headers = ['Category', 'Score']
    for col, header in enumerate(headers):
        worksheet.write(2, col, header, header_format)
    
    # Write grading data dynamically
    row = 3
    reserved_keys = {'Gesamtpunktzahl', 'Erreichbare_punktzahl'}  # Keys to handle separately
    
    # First, handle all non-reserved keys (component scores)
    for key, value in grading_data.items():
        if key not in reserved_keys:
            # Assume values between 0 and 1 are percentages, others are raw scores
            category_name = f"{key.capitalize()} Accuracy"
            if isinstance(value, (int, float)) and 0 <= value <= 1:
                worksheet.write(row, 0, category_name, cell_format)
                worksheet.write(row, 1, value, percent_format)
            else:
                worksheet.write(row, 0, category_name, cell_format)
                worksheet.write(row, 1, value, number_format)
            row += 1
    
    # Then, handle total points if present
    if 'Gesamtpunktzahl' in grading_data and 'Erreichbare_punktzahl' in grading_data:
        worksheet.write(row, 0, 'Total Score', cell_format)
        worksheet.write(row, 1, grading_data['Gesamtpunktzahl'], number_format)
        row += 1
        worksheet.write(row, 0, 'Maximum Points', cell_format)
        worksheet.write(row, 1, grading_data['Erreichbare_punktzahl'], number_format)
    
    # Freeze header rows
    worksheet.freeze_panes(3, 0)
    
    # Close workbook
    workbook.close()

if __name__ == '__main__':
    pass