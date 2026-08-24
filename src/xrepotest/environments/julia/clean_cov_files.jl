#!/usr/bin/env julia
"""
This script cleans up Julia coverage files (.cov) from a specified directory
and its subdirectories.

Usage:
    julia clean_cov_files.jl --dir=/path/to/clean [--dry-run]
"""

using ArgParse

function parse_commandline()
    s = ArgParseSettings("Julia coverage file cleanup tool")
    
    @add_arg_table s begin
        "--dir"
            help = "Directory to clean .cov files from (defaults to current directory)"
            arg_type = String
            default = pwd()
        "--dry-run"
            help = "Only show what would be deleted, don't actually delete"
            action = :store_true
    end
    
    return parse_args(s)
end

function clean_cov_files(dir::String, dry_run::Bool)
    println("🔍 Searching for .cov files in: $dir")
    
    count = 0
    files_by_dir = Dict{String, Vector{String}}()
    
    # Find all .cov files
    for (root, _, files) in walkdir(dir)
        cov_files = filter(f -> endswith(f, ".cov"), files)
        
        if !isempty(cov_files)
            files_by_dir[root] = map(f -> joinpath(root, f), cov_files)
            count += length(cov_files)
        end
    end
    
    # Report findings
    println("\n📊 Found $count .cov files in $(length(files_by_dir)) directories.")
    
    if count == 0
        println("✅ No .cov files to remove.")
        return
    end
    
    # Show distribution by directory
    println("\n📁 Files distribution by directory:")
    for (dir_path, files) in sort(collect(files_by_dir), by=kv->length(kv[2]), rev=true)
        println("  - $(dir_path): $(length(files)) files")
    end
    
    # Delete files if not dry run
    if !dry_run
        println("\n🗑️ Deleting files...")
        deleted = 0
        errors = 0
        
        for (_, files) in files_by_dir
            for file in files
                try
                    rm(file)
                    deleted += 1
                    print("\rDeleted $deleted/$count files...")
                catch e
                    errors += 1
                    println("\n⚠️ Failed to delete $file: $e")
                end
            end
        end
        
        println("\n\n✅ Deleted $deleted files with $errors errors.")
    else
        println("\n🔍 Dry run - no files were deleted.")
        println("   To delete these files, run without the --dry-run flag.")
    end
end

function main()
    args = parse_commandline()
    dir = args["dir"]
    dry_run = args["dry-run"]
    
    if !isdir(dir)
        println("❌ Error: Directory does not exist: $dir")
        exit(1)
    end
    
    clean_cov_files(dir, dry_run)
end

main()
