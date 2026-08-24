#!/usr/bin/env julia

using Pkg
using ArgParse
using JSON
using TOML
using Coverage

function parse_commandline()
    s = ArgParseSettings("Julia coverage analysis for benchmark tests")
    
    @add_arg_table s begin
        "--repo"
            help = "Path to the Julia repository"
            arg_type = String
            required = true
        "--test"
            help = "Path to the test JSONL file"
            arg_type = String
            required = true
        "--output"
            help = "Directory to save coverage results"
            arg_type = String
            required = true
    end

    return parse_args(s)
end

function resolve_module_name(repo_path::String)::String
    project_file = joinpath(repo_path, "Project.toml")
    if isfile(project_file)
        try
            project_data = TOML.parsefile(project_file)
            project_name = get(project_data, "name", "")
            if project_name isa AbstractString && !isempty(strip(project_name))
                return strip(project_name)
            end
        catch e
            @warn "Failed to parse Project.toml name at $project_file: $e"
        end
    end

    repo_name = basename(repo_path)
    return endswith(repo_name, ".jl") ? repo_name[1:end-3] : repo_name
end


function run_test(repo_path, test_file_path, tmp_dir, output_dir)
    mkpath(tmp_dir)
    cd(tmp_dir) do
        Pkg.activate(".", io=devnull)
        
        module_name = resolve_module_name(repo_path)
        
        try
            Pkg.develop(path=repo_path, io=devnull)
        catch e1
            try
                project_file = joinpath(repo_path, "Project.toml")
                if isfile(project_file)
                    Pkg.develop(path=repo_path, io=devnull)
                else
                    src_dir = joinpath(repo_path, "src")
                    if isdir(src_dir)
                        Pkg.generate("TestWrapper", io=devnull)
                        cd("TestWrapper") do
                            mkpath("src/$module_name")
                            cp(src_dir, "src/$module_name")
                        end
                    else
                        return false
                    end
                end
            catch e2
                return false
            end
        end
        
        Pkg.add("Test", io=devnull)
        
        tests = []
        open(test_file_path, "r") do f
            for line in eachline(f)
                push!(tests, JSON.parse(line))
            end
        end
        
        for (i, test_data) in enumerate(tests)
            test_code = get(test_data, "test", "")
            if isempty(test_code)
                continue
            end
            
            # Create the test file
            single_test_file = "test_$i.jl"
            test_content = """
            using Test
            using $module_name
            @testset "test_$i" begin
                $test_code
            end
            """
            open(single_test_file, "w") do f
                write(f, test_content)
            end

            # Create the runner file that collects stats
            count_content = """
            using Test
            to_int(x) = x isa Integer ? Int(x) : (try Int(x) catch; 0 end)

            function extract_test_counts(tc)
                if tc isa NamedTuple
                    return (
                        to_int(get(tc, :passes, 0)) + to_int(get(tc, :cumulative_passes, 0)),
                        to_int(get(tc, :fails, 0)) + to_int(get(tc, :cumulative_fails, 0)),
                        to_int(get(tc, :errors, 0)) + to_int(get(tc, :cumulative_errors, 0)),
                        to_int(get(tc, :broken, 0)) + to_int(get(tc, :cumulative_broken, 0)),
                    )
                end

                if tc isa Tuple
                    n = length(tc)
                    if n >= 8
                        return (
                            to_int(tc[1]) + to_int(tc[5]),
                            to_int(tc[2]) + to_int(tc[6]),
                            to_int(tc[3]) + to_int(tc[7]),
                            to_int(tc[4]) + to_int(tc[8]),
                        )
                    elseif n >= 4
                        return (to_int(tc[1]), to_int(tc[2]), to_int(tc[3]), to_int(tc[4]))
                    end
                end

                props = Set(Symbol.(propertynames(tc)))
                get_prop(name::Symbol) = name in props ? to_int(getproperty(tc, name)) : 0

                return (
                    get_prop(:passes) + get_prop(:cumulative_passes),
                    get_prop(:fails) + get_prop(:cumulative_fails),
                    get_prop(:errors) + get_prop(:cumulative_errors),
                    get_prop(:broken) + get_prop(:cumulative_broken),
                )
            end

            function run_test_and_collect_stats(test_file::String)
                ts = Test.DefaultTestSet("Focal Test")
                Test.push_testset(ts)
                try
                    include(test_file)
                catch e
                    @warn "Error during test execution: \$e"
                end
                result = Test.pop_testset()
                tc = Test.get_test_counts(result)

                total_pass, total_fail, total_error, total_broken = extract_test_counts(tc)

                denom = total_pass + total_fail + total_error + total_broken
                pass_rate = denom > 0 ? total_pass / denom * 100 : 0.0

                println("TEST_RESULTS: \$total_pass,\$total_fail,\$total_error,\$total_broken,\$pass_rate")
                return total_pass, total_fail, total_error, total_broken, pass_rate
            end
            run_test_and_collect_stats("$single_test_file")            
            """
            count_file = "counts_$i.jl"
            open(count_file, "w") do f
                write(f, count_content)
            end
            
            total_pass = 0
            total_fail = 0 
            total_error = 0
            total_broken = 0
            pass_rate = 0.0
            cmd_output = ""
            harness_error = false
            timeout_seconds = 60
            
            try
                start_time = time()
                out_buffer = IOBuffer()
                err_buffer = IOBuffer()
                
                cmd = `julia --project=. --code-coverage=user $count_file`
                process = run(pipeline(cmd, stdout=out_buffer, stderr=err_buffer), wait=false)
                
                timed_out = false
                while process_running(process)
                    if time() - start_time > timeout_seconds
                        kill(process)
                        timed_out = true
                        break
                    end
                    sleep(0.1)
                end
                
                if timed_out
                    cmd_output = "⏱️ Test execution timed out"
                    total_error = 1
                    harness_error = true
                else
                    wait(process)
                    cmd_output = String(take!(out_buffer))
                    err_output = String(take!(err_buffer))
                    if !isempty(err_output)
                        cmd_output = cmd_output * "\nSTDERR:\n" * err_output
                    end
                    
                    result_match = match(r"TEST_RESULTS: (\d+),(\d+),(\d+),(\d+),([\d\.]+)", cmd_output)
                    if result_match !== nothing
                        total_pass = parse(Int, result_match[1])
                        total_fail = parse(Int, result_match[2])
                        total_error = parse(Int, result_match[3])
                        total_broken = parse(Int, result_match[4])
                        pass_rate = parse(Float64, result_match[5])
                    else
                        total_error = 1
                        harness_error = true
                    end
                end
            catch e
                cmd_output = "❌ Test execution failed: $e"
                total_error = 1
                harness_error = true
            end

            # Coverage processing
            filepath = get(test_data, "file_path", "")
            filepath = strip(filepath)
            path_parts = split(filepath, r"[/\\]")
            file_name = path_parts[end]

            # Selective cleanup of unrelated .cov files
            for (root, dirs, files) in walkdir(repo_path)
                for file in files
                    if endswith(file, ".cov") && !occursin(file_name, file)
                        rm(joinpath(root, file), force=true)
                    end
                end
            end

            process_coverage(repo_path, tmp_dir, output_dir, test_data, total_pass, total_fail, total_error, total_broken, pass_rate, cmd_output, harness_error)

            # Final cleanup of .cov files for this test
            for (root, dirs, files) in walkdir(repo_path)
                for file in files
                    if endswith(file, ".cov")
                        rm(joinpath(root, file), force=true)
                    end
                end
            end
        end
    end
    return true
end

function process_coverage(repo_path, tmp_dir, output_dir, test_data, total_pass, total_fail, total_error, total_broken, pass_rate, cmd_output, harness_error)
    cd(tmp_dir) do
        src_dir = joinpath(repo_path, "src")
        if !isdir(src_dir)
            return
        end

        file_path_rel = get(test_data, "file_path", "")
        file_path_rel = strip(file_path_rel)
        file_path_rel = startswith(file_path_rel, "/") ? file_path_rel[2:end] : file_path_rel
        
        path_parts = split(file_path_rel, r"[/\\]")
        if length(path_parts) > 1 && endswith(path_parts[1], ".jl")
            file_path_rel = join(path_parts[2:end], "/")
        end
        
        file_path_abs = joinpath(repo_path, file_path_rel)
        if !isfile(file_path_abs)
            return
        end

        filecov = process_file(file_path_abs)
        covered = 0
        total = 0

        for (i, cov) in enumerate(filecov.coverage)
            if test_data["start_line"] <= i <= test_data["end_line"]
                total += 1
                if cov !== nothing && cov != 0
                    covered += 1
                end
            end
        end

        info = Dict()
        info["function_name"] = test_data["function_name"]
        info["test"] = test_data["test"]
        info["focal_code"] = test_data["focal_code"]
        info["test_idx"] = get(test_data, "test_idx", 0)
        info["covered_lines"] = covered
        info["total_lines"] = total
        info["coverage_percent"] = total > 0 ? (covered / total) * 100 : 0.0
        info["pass"] = total_pass
        info["fail"] = total_fail
        info["error"] = total_error
        info["broken"] = total_broken
        info["pass_rate"] = pass_rate
        info["log"] = cmd_output
        info["harness_error"] = harness_error
        
        repo_name = basename(repo_path)
        output_file = joinpath(output_dir, "$(repo_name).jsonl")

        open(output_file, "a") do f
            write(f, JSON.json(info) * "\n")
        end      
    end
end

function main()
    args = parse_commandline()
    repo_path = args["repo"]
    test_file = args["test"]
    output_dir = args["output"]
    
    if !isdir(repo_path) || !isfile(test_file)
        exit(1)
    end
    
    mkpath(output_dir)
    
    # Initial cleanup
    for (root, dirs, files) in walkdir(repo_path)
        for file in files
            if endswith(file, ".cov")
                rm(joinpath(root, file), force=true)
            end
        end
    end
    
    tmp_dir = mktempdir()
    try
        run_test(repo_path, test_file, tmp_dir, output_dir)
    catch e
        println("Error during coverage analysis: $e")
    finally
        rm(tmp_dir, recursive=true, force=true)
    end
end

main()
