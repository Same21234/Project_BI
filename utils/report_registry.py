
# ==========================================================
# REPORT REGISTRY
# ==========================================================

from reports.Branchwise_Analysis import render_report as branch_report
from reports.ATS_Analysis import ATS_Analysis
from reports.Monthly_Disbursement import Monthly_Disbursement
from reports.ATS_Disb_MoM import ATS_Disb_MoM
from reports.Vintage_Analysis import render_report as vintage_report
from reports.PIN_Code_Analysis import render_report as pin_code_report

# State Wise Analysis report
from reports.State_Wise_Analysis import render_report as state_wise_report


# ==========================================================
# REGISTER ALL REPORTS
# ==========================================================

REPORTS = {

    "🏢 Branch Wise Analysis": {
        "view": "branch_wise_analysis",
        "function": branch_report,
    },

    # NEW REPORT: State Wise Analysis
    # No month slicer required for this report
    "🏢 PAR Analysis": {
        "view": None,
        "function": state_wise_report,
        "uses_internal_filters": True,
    },

    "🧮 ATS Analysis": {
        "view": "ats_analysis",
        "function": ATS_Analysis,
    },

    "📊 Monthly Disb": {
        "view": "Monthly Disbursement",
        "function": Monthly_Disbursement,
    },

    "📈 ATS_Disb_MoM": {
        "view": "ATS_Disb_MoM",
        "function": ATS_Disb_MoM,
    },

    "🧭 Vintage Analysis": {
        "view": "vintage_analysis",
        "function": vintage_report,
        "uses_internal_filters": True,
    },

    "🗺️ PIN Code Analysis": {
        "view": "pin_code_analysis",
        "function": pin_code_report,
        "uses_internal_filters": True,
    },

}
